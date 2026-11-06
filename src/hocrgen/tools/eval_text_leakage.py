"""E2d2: training-text leakage check for real-scan evaluation references (word n-gram overlap).

A real-scan reference whose text a recognizer was trained on does not measure recognition of unseen text. This
check compares each evaluation reference with the text corpora that synthetic training pages were rendered from
(for example hocrsyngen's ``hebrew_lines_*``, ``hebrew_mixed_lines_*`` and ``hebrew_typographic_lines_*``, or a
future pinned Project Ben-Yehuda corpus, hocrsyngen S15a).

Both sides are compared as consonantal word sequences: NFC, bidi controls, bracketed footnote marks ``[n]``,
Hebrew points and cantillation and all punctuation removed (dashes and maqaf become spaces), split on whitespace.
Corpus n-grams never cross a corpus line; reference n-grams run across the whole page.

The E2d policy (``LEAKAGE_POLICY``): a page that shares **any word 8-gram** with a training corpus is excluded from
the scored set; the share of its word 3-grams found in the corpora is reported, and a page above the flag share is
listed for review. Reports carry counts and ids only, never text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Mapping

from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_evaluation import _BIDI_CONTROLS, _HEBREW_MARKS, reference_text
from hocrgen.manifests.models import BenchmarkTranscriptionReferenceRecord

LEAKAGE_REPORT_SCHEMA = "hocrgen_eval_text_leakage.v1"
LEAKAGE_POLICY = {
    "tokens": "consonantal words: NFC; bidi controls, [n] footnote marks, Hebrew points/cantillation and punctuation removed",
    "exclude_if_shared_word_ngrams": {"n": 8, "at_least": 1},
    "flag_if_word_3gram_share_above": 0.2,
}
_FOOTNOTE_MARK = re.compile(r"\[[0-9]{1,3}\]")


def leakage_tokens(text: str) -> list[str]:
    """Consonantal word tokens used for overlap checks (punctuation and points dropped, dashes split words)."""

    text = _FOOTNOTE_MARK.sub(" ", unicodedata.normalize("NFC", text))
    folded = []
    for char in text:
        if char in _BIDI_CONTROLS or char in _HEBREW_MARKS:
            continue
        category = unicodedata.category(char)
        if category == "Pd" or char.isspace():
            folded.append(" ")
        elif not category.startswith("P"):
            folded.append(char)
    return "".join(folded).split()


def _key(words: Iterable[str]) -> bytes:
    return hashlib.blake2b("\u0001".join(words).encode("utf-8"), digest_size=12).digest()


def ngram_keys(tokens: list[str], n: int) -> list[bytes]:
    return [_key(tokens[index:index + n]) for index in range(len(tokens) - n + 1)]


class CorpusIndex:
    """Hashed word n-gram sets of one or more corpora (n-grams never cross a corpus line)."""

    def __init__(self, sizes: Iterable[int] = (3, 8)) -> None:
        self.sizes = tuple(sorted(set(sizes)))
        self.grams: dict[int, set[bytes]] = {n: set() for n in self.sizes}
        self.corpora: list[dict[str, object]] = []

    def add(self, name: str, lines: Iterable[str], *, sha256: str | None = None) -> None:
        count = words = 0
        for line in lines:
            tokens = leakage_tokens(line)
            count += 1
            words += len(tokens)
            for n in self.sizes:
                self.grams[n].update(ngram_keys(tokens, n))
        self.corpora.append({"name": name, "sha256": sha256, "lines": count, "words": words})

    def add_file(self, name: str, path: Path) -> None:
        raw = path.read_bytes()
        self.add(name, raw.decode("utf-8").splitlines(), sha256=hashlib.sha256(raw).hexdigest())

    def overlap(self, tokens: list[str]) -> dict[str, object]:
        result: dict[str, object] = {"words": len(tokens)}
        for n in self.sizes:
            keys = ngram_keys(tokens, n)
            shared = sum(key in self.grams[n] for key in keys)
            result[f"word_{n}grams"] = len(keys)
            result[f"shared_word_{n}grams"] = shared
            result[f"word_{n}gram_share"] = shared / len(keys) if keys else None
        return result


def leakage_verdict(overlap: Mapping[str, object], policy: Mapping[str, object] = LEAKAGE_POLICY) -> str:
    """``exclude`` (shares a long n-gram), ``flag`` (high 3-gram share) or ``clear``."""

    rule = policy["exclude_if_shared_word_ngrams"]
    if int(overlap.get(f"shared_word_{rule['n']}grams") or 0) >= int(rule["at_least"]):
        return "exclude"
    share = overlap.get("word_3gram_share")
    if share is not None and float(share) > float(policy["flag_if_word_3gram_share_above"]):
        return "flag"
    return "clear"


def check_texts(texts: Mapping[str, str], index: CorpusIndex) -> dict[str, object]:
    """Overlap and verdict per item id; ids and counts only."""

    items = []
    for item_id in sorted(texts):
        overlap = index.overlap(leakage_tokens(texts[item_id]))
        items.append({"item_id": item_id, **overlap, "verdict": leakage_verdict(overlap)})
    counts = {verdict: sum(item["verdict"] == verdict for item in items) for verdict in ("exclude", "flag", "clear")}
    return {"schema_version": LEAKAGE_REPORT_SCHEMA, "policy": LEAKAGE_POLICY, "corpora": index.corpora,
            "counts": counts, "items": items}


def reference_manifest_texts(manifest_path: Path) -> dict[str, str]:
    """Scoped text of every transcription reference listed in a ``benchmark_reference_manifest.v1``."""

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    texts = {}
    for item in payload.get("items", []):
        reference = item.get("transcription_reference")
        if not reference:
            continue
        record = BenchmarkTranscriptionReferenceRecord.model_validate(
            json.loads((manifest_path.parent / reference["path"]).read_text(encoding="utf-8")))
        texts[item["item_id"]] = reference_text(record)
    return texts


def jsonl_texts(path: Path) -> dict[str, str]:
    texts = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            texts[record["item_id"]] = record["text"]
    return texts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Word n-gram overlap of evaluation references with training corpora")
    parser.add_argument("--reference-manifest", type=Path, action="append", default=[])
    parser.add_argument("--texts", type=Path, action="append", default=[], help="JSONL {item_id, text}")
    parser.add_argument("--corpus", action="append", default=[], metavar="NAME=PATH", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hold-out-output", type=Path, default=None,
                        help="Write {item_id: reason} for every excluded page (wikisource_eval_references --hold-out)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    texts: dict[str, str] = {}
    for path in args.reference_manifest:
        texts.update(reference_manifest_texts(path))
    for path in args.texts:
        texts.update(jsonl_texts(path))
    if not texts:
        raise StageExecutionError("no reference texts to check")
    index = CorpusIndex()
    for spec in args.corpus:
        name, _, path = spec.partition("=")
        if not name or not path:
            raise StageExecutionError(f"--corpus takes NAME=PATH, got {spec!r}")
        index.add_file(name, Path(path))
    report = check_texts(texts, index)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.hold_out_output is not None:
        n = LEAKAGE_POLICY["exclude_if_shared_word_ngrams"]["n"]
        held = {item["item_id"]: f"training_text_overlap: {item['shared_word_%dgrams' % n]} shared word {n}-grams "
                                 "with the training corpora"
                for item in report["items"] if item["verdict"] == "exclude"}
        args.hold_out_output.write_text(json.dumps(held, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"counts": report["counts"], "corpora": len(index.corpora)}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
