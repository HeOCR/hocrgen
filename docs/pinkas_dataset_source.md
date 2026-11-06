# BGU Pinkas Dataset source (F8d2, F8d3, F8d3b)

Source id `pinkas_dataset_bgu`, fetcher `pinkas_dataset`. Source proposal: `HeOCR/hocrgen#105`. Plan: [`planning/tasks/f8-real-source-map.md`](../planning/tasks/f8-real-source-map.md) (`F8d2` admitted the source, `F8d3` adds per-line language tags).

Each item is one handwritten page of the Frankfurt am Main community pinkas, NLI Ms. Heb. 4°662, with the BGU Pinkas Dataset's upstream PAGE XML (Zenodo 3569694): region, line and word polygons and text. The snapshot is under `src/hocrgen/data/pinkas_dataset_bgu/snapshot/`.

## Status and rights

- `status: review_only`, `default_public_release: false`. Included only in `profile_review_v1`; not in `profile_open_v1`.
- Annotations: `CC-BY-4.0` / `open_with_attribution` (the Zenodo licence field). Scans: the NLI IIIF manifest's `public-domain-free-use` slug, decided by the F8c gate over a pinned manifest capture. The evidence is in the [F8d2 findings](../planning/tasks/f8-real-source-map.md#f8d2-findings-2026-11-06).
- The text is human-annotated (semi-automatic segmentation, then corrected by a Hebrew paleographer), but not attested or adjudicated under F2: `not_adjudicated`, `reference_eligible: false`.

## Line language and evaluation scope (F8d3)

The line text mixes Hebrew and Western Yiddish, often within one line. Maintainer decision 8 (2026-11-06, clarified by the maintainer the same day; [`planning/decisions/2026-11-06-f8-real-source-decisions.md`](../planning/decisions/2026-11-06-f8-real-source-decisions.md)):

- **Hebrew lines** may be used with full Hebrew scope: training, character-level evaluation, and word-level and language-level Hebrew evaluation. Nothing is excluded.
- **Yiddish lines** keep the decision-6 scope: training and character-level evaluation only.
- A line counts as Hebrew **only** through an explicit, reviewable per-line tag. Untagged lines keep `character_level_only`. Tags are never inferred silently from a heuristic.

### Tags

Tags live in the sidecar `line_language_tags.yaml` (format `hocrgen.pinkas_line_language_tags.v1`), named by `line_language_tags_path` in `snapshot.yaml`. The typed models are in `hocrgen.fetchers.pinkas_line_language`. Each page block names its `entry_id` and the `annotation_sha256` of the PAGE XML the tags were made against. Each line tag has these fields:

| Field | Meaning |
| --- | --- |
| `line_id` | The PAGE XML `TextLine` id. |
| `text` | The exact (NFC) line text the tag was made against. |
| `language` | `he`, `yi`, `mixed` or `unknown`. |
| `tag_source` | `human` or `agent_proposed`. |
| `tagged_by` | The reviewer's name for `human`; always `hocrgen.tools.pinkas_line_language` for `agent_proposed`. |
| `tagged_at` | The date of the tag. |
| `rationale` | Why this language. |
| `proposal` | Optional. The proposal tool's language, confidence and evidence, kept for audit after a human decision. |

The models reject an `agent_proposed` tag with any other `tagged_by`, a `human` tag that names the tool, unknown languages or sources, empty rationales, extra fields, and duplicate lines or pages.

### Scope derivation

`line_scope_fields` in `hocrgen.fetchers.pinkas_line_language` is the only place a line's scope is decided. It reads the line's pinned text first, then its tag:

| Line and tag | `evaluation_scope` | Allowed uses | Reason code |
| --- | --- | --- | --- |
| no Hebrew-script letter, any tag or none | `character_level_only`, `scope_neutral: true` | training, character-level evaluation | `scope_neutral_no_hebrew_letters` |
| `human`, `he` | `full_hebrew` | training, character-level, word-level Hebrew and language-level Hebrew evaluation; nothing excluded | `human_tagged_he` |
| `human`, `yi` / `mixed` / `unknown` | `character_level_only` | training, character-level evaluation | `human_tagged_yi` / `_mixed` / `_unknown` |
| any `agent_proposed` tag | `character_level_only` | training, character-level evaluation | `agent_proposed_tag_is_advisory` |
| no tag | `character_level_only` | training, character-level evaluation | `untagged` |
| stale tag | `character_level_only` | training, character-level evaluation | `tag_stale` |

- Every `character_level_only` row excludes both `word_level` and `language_level_hebrew`. The `language_level_hebrew` exclusion exists to keep Yiddish from being treated as Hebrew-language data. A human-tagged Hebrew line is Hebrew, so it has no exclusions (the maintainer's clarification of decision 8, 2026-11-06).
- **Scope-neutral lines (F8d3b).** A line whose pinned text has no letter in U+05D0–U+05EA (digits, punctuation, years, an empty line) is scope-neutral. This is decided from the text, never from a tag, so a human `he` tag on such a line changes nothing. A scope-neutral line never gets Hebrew scope itself, and the page rule ignores it.
- A tag is **stale** when its `text` differs from the parsed line, or when its page block's `annotation_sha256` differs from the entry's. A stale tag never widens scope.
- A `mixed` line is not a Hebrew line, so it stays `character_level_only`.
- **Page scope.** The entries keep the pinned page default `usage_scope.evaluation_scope: character_level_only`. The derived page scope is `full_hebrew` only when the page has at least one text line and every text line (every line that is not scope-neutral) is human-tagged `he`, and so `full_hebrew`. So while any text line is untagged, stale, advisory or not Hebrew, the page stays `character_level_only`. Page numbers, years and empty lines never hold a page back.

### What evaluators read

- `load_entry_line_scopes(root, entry, tag_file)` in `hocrgen.fetchers.pinkas_dataset` returns one `LineEvaluationScope` per line, in reading order. Each carries the tag's language, source and reviewer, the derived scope and reason, and the line geometry in thumbnail pixels.
- Candidate metadata carries:
  - `line_scopes`: the same records without geometry;
  - `line_scope_summary`: counts, reasons, and the `full_hebrew` and scope-neutral line ids;
  - `evaluation_scope`: the derived page scope.
- Source health adds the `pinkas_dataset_line_language_tags` check. It counts tags by source and language, and lines by derived scope (`full_hebrew`, `character_level_only`, `scope_neutral`). It fails on a malformed sidecar or any stale tag.
- `F8d3` changes no scorer, no `profile_open_v1` membership and no `benchmark_v1` membership. Scoring that uses line scope is later work.

## Proposing tags

The operator tool writes `agent_proposed` tags for every line that has no human tag. It never overwrites a human tag:

```
PYTHONPATH=src python -m hocrgen.tools.pinkas_line_language propose --tagged-at 2026-11-06
PYTHONPATH=src python -m hocrgen.tools.pinkas_line_language check
```

`propose --dry-run` prints the sidecar without writing it. `check` validates the sidecar against the snapshot, prints counts, and exits 1 on any stale tag. Both are network-free.

The method, `pinkas_line_lexicon.v1`, is small on purpose, so that a reviewer can see why each line got its proposal:

1. **Tokenize.** Split the line on whitespace and strip surrounding punctuation. Geresh and gershayim stay, so `הנ"ל` and `אונ'` remain one token each.
2. **Match lexicons.** Each token is matched exactly against two closed lists in the tool:
   - `YIDDISH_MARKERS`: Western Yiddish function words and auxiliaries, such as `אונ'`, `דז`, `ער`, `זאל`, `הוט`, `גוועזן`, `קיין`, `מיט`;
   - `HEBREW_MARKERS`: Hebrew function words and the register's abbreviations and signature formulas, such as `על`, `אשר`, `הנ"ל`, `יצ"ו`, `ז"ל`, `ונאם`, `בן`.
3. **Note spellings.** On tokens that match neither list, the tool records weak Yiddish orthography markers: initial `וו`, a `יי` digraph, a final `ען`, or the ligatures `װ ױ ײ`. These never decide a language, and they flag plene Hebrew spellings too, such as `אייר`.
4. **Decide.**
   - Both kinds of marker give `mixed`.
   - Only Yiddish markers give `yi`.
   - Only Hebrew markers give `he`.
   - Neither gives `unknown`.
   - A line with no Hebrew-script letter (a numeral or an empty line) gives `unknown`.
5. **Set confidence.**
   - `high`: two or more deciding markers.
   - `medium`: one deciding marker.
   - `low`: an `unknown` line that has letters, or a `he` proposal that carries orthography markers.

Each proposal records its matched markers and a one-line rationale. The lexicons were written while reading the fixture pages, so on other pages they will miss vocabulary. That is one reason the proposals are advisory.

**Committed proposals (2026-11-06).** The two fixture pages have 79 lines:

| Proposed language | Lines | Confidence |
| --- | --- | --- |
| `he` | 57 | 42 high, 3 medium, 12 low |
| `mixed` | 13 | 9 high, 4 medium |
| `yi` | 0 | |
| `unknown` | 9 | numerals and one empty line |

No line is human-tagged yet, so every line is `character_level_only`. The 9 `unknown` lines are also scope-neutral. The other 70 text lines are the ones a reviewer needs to decide.

## Review procedure

Only a human confirms or overrides a tag. An agent never sets `tag_source: human`, and never stands in for a reviewer.

1. **Compare.** Open `src/hocrgen/data/pinkas_dataset_bgu/snapshot/line_language_tags.yaml` next to the page thumbnail, or the NLI canvas named in `entries.jsonl`.
2. **Decide each line.** Read the line's `text` and decide its language:
   - `he` only if the whole line is Hebrew (Hebrew or Aramaic legal formulae, names and dates included);
   - `mixed` if it holds any Yiddish word or phrase;
   - `yi` if it is Yiddish throughout;
   - `unknown` for lines you cannot judge.

   Numerals and empty lines are scope-neutral whatever their tag, so they need no decision.
3. **Edit the tag.** For each line you have reviewed:
   - set `language`;
   - set `tag_source: human`;
   - set `tagged_by` to your own name;
   - set `tagged_at` to the review date;
   - set `rationale` to a short reason, such as `confirmed proposal` or `contains Yiddish צייט`.

   Leave `text`, `line_id` and the `proposal` block unchanged. The proposal stays as the audit record of what the tool said.
4. **Check.** Run the tool's `check` command and the source tests. A changed `text` makes the tag stale, and `check` fails.
5. **Open a PR.** Name the reviewer in the PR. Re-running `propose` later keeps human tags, and refreshes only the advisory ones.

**If the PAGE XML changes.** Human tags made against the old annotation checksum become stale, and give no Hebrew scope. `propose` refuses to rebind them to the new checksum. A human re-reviews those lines and updates the page block's `annotation_sha256` before proposals are refreshed.

A partial review is fine. Reviewed lines with `he` become `full_hebrew`. Every other line stays `character_level_only`. The page becomes `full_hebrew` once a human has tagged every text line `he`.
