"""Operator tool: propose per-line language tags for `pinkas_dataset_bgu` and check the reviewed sidecar.

    python -m hocrgen.tools.pinkas_line_language propose [--snapshot-root DIR] [--tagged-at YYYY-MM-DD] [--dry-run]
    python -m hocrgen.tools.pinkas_line_language check [--snapshot-root DIR]

`propose` writes `agent_proposed` tags only. They are advisory and never change a line's evaluation scope; only a
human reviewer, by setting `tag_source: human` and their own name in `tagged_by`, can do that (see
`docs/pinkas_dataset_source.md`). Existing human tags are never overwritten.

The method is deliberately small and transparent, so a reviewer can see why each line got its proposal:

1. Tokenize the NFC line text on whitespace and strip surrounding punctuation, keeping geresh and gershayim
   (`'`, `"`, `׳`, `״`), which mark Hebrew abbreviations such as `הנ"ל` and Yiddish `אונ'`.
2. Match each token exactly against two closed lexicons: Western Yiddish function words and auxiliaries
   (`YIDDISH_MARKERS`) and Hebrew function words and formulaic abbreviations (`HEBREW_MARKERS`).
3. Record weak Yiddish orthography markers on unmatched tokens (`orthography_markers`): word-initial `וו`, a `יי`
   digraph, a final `ען`, or a Yiddish ligature (`װ ױ ײ`). They never decide a language; they lower confidence.
4. Decide: Yiddish and Hebrew markers both present gives `mixed`; only Yiddish gives `yi`; only Hebrew gives `he`;
   none gives `unknown`; a line without a Hebrew-script letter (U+05D0-U+05EA: a numeral, or empty) gives
   `unknown`. Such a line is scope-neutral whatever its tag (F8d3b).
5. Confidence: `high` with two or more deciding markers and no orthography markers, `medium` with one, and `low`
   for `unknown` lines with letters and for any `he` proposal that carries orthography markers.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from hocrgen.config.loader import package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.pinkas_dataset import load_entry_line_scopes, load_entry_page_lines, load_pinkas_dataset_snapshot
from hocrgen.fetchers.pinkas_line_language import (
    AGENT_PROPOSER_ID,
    LINE_LANGUAGE_TAGS_FORMAT,
    LineLanguageProposal,
    LineLanguageTag,
    LineLanguageTagFile,
    PageLineLanguageTags,
    has_hebrew_letter,
    line_language_tags_path,
    load_line_language_tags,
    page_scope_summary,
    tag_file_problems,
)

SOURCE_ID = "pinkas_dataset_bgu"
PROPOSAL_METHOD = "pinkas_line_lexicon.v1"
DEFAULT_SNAPSHOT_ROOT = package_root() / "data" / "pinkas_dataset_bgu" / "snapshot"

# Western Yiddish function words, pronouns, auxiliaries and particles as spelled in the Frankfurt pinkas.
YIDDISH_MARKERS = frozenset(
    {
        "אונ'", "אונ", "אודר", "איז", "איזט", "איין", "אים", "איר", "אלש", "דאש", "דורך", "דז", "דיא", "דיזר",
        "דעם", "דער", "דש", "האט", "הוט", "הער", "ואר", "וועלכר", "ווערין", "ווייטר", "ווארין", "ור", "זא",
        "זאל", "זאלט", "זאלן", "זיא", "זיין", "זיינה", "זיך", "זעלן", "מיט", "נאך", "נוך", "ניט", "ער", "פון",
        "צו", "קומן", "קומט", "קיין", "קיינר", "גוועזן", "הלט", "לנג",
    }
)
# Hebrew function words and the community register's formulaic abbreviations and signature formulas.
HEBREW_MARKERS = frozenset(
    {
        "של", "את", "על", "אשר", "לא", "ולא", "כי", "אם", "ואם", "כל", "וכל", "גם", "עם", "אל", "או", "עד",
        "זה", "הזה", "זאת", "הזאת", "הוא", "היה", "יהיה", "יהא", "לו", "אין", "רק", "אך", "אמנם", "אזי", "אז",
        "ואז", "בכן", "כאשר", "כמו", "שלא", "מן", "מכל", "לשום", "שום", "אחד", "יום", "מהיום", "היום", "כהיום",
        "יען", "וביען", "פה", "בכאן", "לכאן", "אצלינו", "עמנו", "הנ\"ל", "כנ\"ל", "יצ\"ו", "ז\"ל", "זלה\"ה",
        "זצלה\"ה", "זצל", "לפ\"ק", "ב\"ר", "בר", "בן", "לא\"א", "בלא\"א", "לאא\"מ", "הר\"ר", "מהר\"ר", "מה\"ר",
        "נאם", "ונאם", "ונא'", "ונאום", "נאו'", "ונאו'", "הקטן", "האב\"ד", "ע\"כ", "ע\"י", "עכ\"פ", "ועכ\"פ",
        "מכ\"ש",
    }
)
YIDDISH_LIGATURES = ("װ", "ױ", "ײ")
STRIP_CHARS = ",.:;!?()[]{}#|-–—*"


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in unicodedata.normalize("NFC", text).split():
        token = raw.strip(STRIP_CHARS).replace("׳", "'").replace("״", '"')
        if token:
            tokens.append(token)
    return tokens


def _orthography_marker(token: str) -> bool:
    bare = token.strip("'\"")
    return (
        bare.startswith("וו")
        or "יי" in bare
        or bare.endswith("ען")
        or any(ligature in bare for ligature in YIDDISH_LIGATURES)
    )


def _unique(tokens: list[str]) -> list[str]:
    return list(dict.fromkeys(tokens))


def propose_line_language(text: str) -> tuple[LineLanguageProposal, str]:
    """Propose a language for one line; return the proposal and a one-line human-readable rationale."""

    if not has_hebrew_letter(text):
        proposal = LineLanguageProposal(method=PROPOSAL_METHOD, language="unknown", confidence="high")
        return proposal, f"{PROPOSAL_METHOD} proposal (high): no Hebrew-script letters (a numeral or an empty line)"
    tokens = tokenize(text)
    yiddish = _unique([token for token in tokens if token in YIDDISH_MARKERS])
    hebrew = _unique([token for token in tokens if token in HEBREW_MARKERS])
    orthography = _unique(
        [token for token in tokens if token not in YIDDISH_MARKERS and token not in HEBREW_MARKERS and _orthography_marker(token)]
    )
    yi_hits = sum(1 for token in tokens if token in YIDDISH_MARKERS)
    he_hits = sum(1 for token in tokens if token in HEBREW_MARKERS)
    if yi_hits and he_hits:
        language, confidence = "mixed", "high" if min(yi_hits, he_hits) >= 2 else "medium"
    elif yi_hits:
        language, confidence = "yi", "high" if yi_hits >= 2 else "medium"
    elif he_hits:
        language = "he"
        confidence = "low" if orthography else ("high" if he_hits >= 2 else "medium")
    else:
        language, confidence = "unknown", "low"
    proposal = LineLanguageProposal(
        method=PROPOSAL_METHOD,
        language=language,
        confidence=confidence,
        yiddish_markers=yiddish,
        hebrew_markers=hebrew,
        orthography_markers=orthography,
    )
    parts = [f"{yi_hits} Yiddish and {he_hits} Hebrew lexicon marker tokens"]
    if orthography:
        parts.append(f"possible Yiddish spellings to check: {' '.join(orthography)}")
    return proposal, f"{PROPOSAL_METHOD} proposal ({confidence}): " + "; ".join(parts)


def build_proposals(root: Path, tagged_at: date) -> tuple[LineLanguageTagFile, list[str]]:
    """Propose tags for every line of every snapshot entry, keeping any existing human tag untouched."""

    snapshot, entries = load_pinkas_dataset_snapshot(root)
    existing = load_line_language_tags(root, snapshot)
    notes: list[str] = []
    pages: list[PageLineLanguageTags] = []
    for entry in sorted(entries, key=lambda record: record["entry_id"]):
        page = load_entry_page_lines(root, entry)
        old_page = existing.page(entry["entry_id"]) if existing is not None else None
        human = {tag.line_id: tag for tag in (old_page.lines if old_page else []) if tag.tag_source == "human"}
        if human and old_page is not None and old_page.annotation_sha256 != entry["annotation"]["sha256"]:
            # Rebinding would silently revive human tags made against another annotation. A human re-reviews first.
            raise StageExecutionError(
                f"{entry['entry_id']}: human tags were made against annotation {old_page.annotation_sha256[:12]}, "
                f"not {entry['annotation']['sha256'][:12]}; re-review them (and update annotation_sha256) before re-proposing"
            )
        line_ids = {line.line_id for line in page.lines}
        for line_id in sorted(set(human) - line_ids):
            notes.append(f"{entry['entry_id']}:{line_id}: human tag kept for a line no longer in the PAGE XML")
        tags: list[LineLanguageTag] = []
        for line in page.lines:
            if line.line_id in human:
                tags.append(human[line.line_id])
                if human[line.line_id].text != line.text:
                    notes.append(f"{entry['entry_id']}:{line.line_id}: human tag kept but its text no longer matches")
                continue
            proposal, rationale = propose_line_language(line.text)
            tags.append(
                LineLanguageTag(
                    line_id=line.line_id,
                    text=line.text,
                    language=proposal.language,
                    tag_source="agent_proposed",
                    tagged_by=AGENT_PROPOSER_ID,
                    tagged_at=tagged_at,
                    rationale=rationale,
                    proposal=proposal,
                )
            )
        tags.extend(human[line_id] for line_id in sorted(set(human) - line_ids))
        pages.append(PageLineLanguageTags(entry_id=entry["entry_id"], annotation_sha256=entry["annotation"]["sha256"], lines=tags))
    tag_file = LineLanguageTagFile(
        format=LINE_LANGUAGE_TAGS_FORMAT,
        source_id=SOURCE_ID,
        review_procedure=(
            "agent_proposed tags are advisory and never change scope. To confirm or override a line, a human "
            "reviewer sets language, tag_source: human, tagged_by: <their name>, tagged_at: <date> and a rationale, "
            "keeping the proposal block. Only tag_source human with language he gives a line full Hebrew scope. "
            "See docs/pinkas_dataset_source.md."
        ),
        proposal_method=(
            f"{PROPOSAL_METHOD}: exact-token match against closed Western Yiddish and Hebrew marker lexicons "
            "(hocrgen.tools.pinkas_line_language); both present -> mixed, Yiddish only -> yi, Hebrew only -> he, "
            "neither -> unknown; orthography markers (initial וו, יי, final ען, ligatures) only lower confidence"
        ),
        pages=pages,
    )
    return tag_file, notes


class _ReviewDumper(yaml.SafeDumper):
    """YAML for hand editing: no anchors or aliases, and marker lists on one line."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def _represent_list(dumper: yaml.SafeDumper, data: list[Any]) -> yaml.Node:
    flow = all(isinstance(item, str) for item in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_ReviewDumper.add_representer(list, _represent_list)


def dump_tag_file(tag_file: LineLanguageTagFile) -> str:
    payload: dict[str, Any] = tag_file.model_dump(mode="python", exclude_none=True)
    return yaml.dump(payload, Dumper=_ReviewDumper, sort_keys=False, allow_unicode=True, width=1000)


def summarize(root: Path) -> tuple[dict[str, Any], list[str]]:
    """Validate the sidecar against the snapshot and count tags and derived scopes."""

    snapshot, entries = load_pinkas_dataset_snapshot(root)
    tag_file = load_line_language_tags(root, snapshot)
    counts: dict[str, dict[str, int]] = {}
    confidence: dict[str, int] = {}
    pages: dict[str, tuple[str, list[Any]]] = {}
    page_scopes: dict[str, dict[str, Any]] = {}
    for entry in entries:
        page = load_entry_page_lines(root, entry)
        pages[entry["entry_id"]] = (entry["annotation"]["sha256"], page.lines)
        page_scopes[entry["entry_id"]] = page_scope_summary(load_entry_line_scopes(root, entry, tag_file, page))
    problems = tag_file_problems(tag_file, pages) if tag_file is not None else []
    for page_tags in tag_file.pages if tag_file is not None else []:
        for tag in page_tags.lines:
            bucket = counts.setdefault(tag.tag_source, {})
            bucket[tag.language] = bucket.get(tag.language, 0) + 1
            if tag.tag_source == "agent_proposed" and tag.proposal is not None:
                key = f"{tag.proposal.language}:{tag.proposal.confidence}"
                confidence[key] = confidence.get(key, 0) + 1
    tagged = sum(len(page_tags.lines) for page_tags in tag_file.pages) if tag_file is not None else 0
    return (
        {
            "sidecar": str(line_language_tags_path(root, snapshot).name) if tag_file is not None else None,
            "line_count": sum(len(lines) for _, lines in pages.values()),
            "tagged_line_count": tagged,
            "tags_by_source_and_language": {source: dict(sorted(langs.items())) for source, langs in sorted(counts.items())},
            "agent_proposals_by_confidence": dict(sorted(confidence.items())),
            "page_scopes": {entry_id: summary["page_evaluation_scope"] for entry_id, summary in sorted(page_scopes.items())},
            "full_hebrew_line_count": sum(summary["full_hebrew_line_count"] for summary in page_scopes.values()),
            "scope_neutral_line_count": sum(summary["scope_neutral_line_count"] for summary in page_scopes.values()),
        },
        problems,
    )


def _print_summary(summary: dict[str, Any], problems: list[str]) -> None:
    print(yaml.safe_dump(summary, sort_keys=False, allow_unicode=True).rstrip())
    for problem in problems:
        print(f"stale: {problem}", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Propose and check per-line language tags for pinkas_dataset_bgu.")
    sub = parser.add_subparsers(dest="command", required=True)
    propose = sub.add_parser("propose", help="write agent_proposed tags for every line without a human tag")
    propose.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    propose.add_argument("--tagged-at", type=date.fromisoformat, default=date.today())
    propose.add_argument("--dry-run", action="store_true", help="print the summary without writing the sidecar")
    check = sub.add_parser("check", help="validate the sidecar against the snapshot and print counts")
    check.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.snapshot_root
    try:
        if args.command == "propose":
            tag_file, notes = build_proposals(root, args.tagged_at)
            for note in notes:
                print(f"note: {note}", file=sys.stderr)
            if args.dry_run:
                print(dump_tag_file(tag_file))
                return 0
            snapshot, _ = load_pinkas_dataset_snapshot(root)
            line_language_tags_path(root, snapshot).write_text(dump_tag_file(tag_file), encoding="utf-8")
        summary, problems = summarize(root)
    except StageExecutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_summary(summary, problems)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
