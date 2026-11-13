# Training-line text from Knesset protocols (decision 0018)

`hocrgen.tools.knesset_lines` turns born-digital Knesset protocols (DOC / DOCX) into gated training-line text. hocrsyngen
then renders that text in open-licensed fonts (`hocrsyngen render-lines`). Two series share the builder and differ
only in their `Series` record:

| | `plenary` | `committee` |
|---|---|---|
| Set | `knessetplenarylines_v1` | `knessetcommitteelines_v1` |
| Terms | K13–25 | K16–25 |
| Unit id | `plenary:K<k>_<sitting>` | `committee:K<k>_<session id>` (never `knesset_committee:<id>`) |
| Source id | `knesset_plenary_k13_25` | `knesset_committee_protocols_k16plus` |
| Gate | `plenary_private_names_v1` (`gate_stream_lines`) | `committee_private_names_v1` (`gate_committee_lines`) |
| Structural headings | speaker markers prove a heading | none; markers only feed the session denylist |
| Release scope | `publishable` | `committee_release_scope(session_date)`, training only |

**The lines are synthetic: real text, rendered by HeOCR.** Every row records `capture: synthetic_render`,
`label_source: born_digital_protocol_text`, `reference_eligible: false` and `eval_use: never`.

## Run

```bash
python -I kl_runner.py plan PLAN.json --enumeration plenary_units_k13plus.json --series plenary
python -I kl_runner.py capture PLAN.json --cache CACHE
python -I kl_runner.py build OUT --plan PLAN.json --cache CACHE --series plenary --signature "<operator>"
python -I kl_runner.py render OUT --render-dir RENDER   # runs hocrsyngen render-lines, then joins its manifest
python -I kl_runner.py verify OUT
```

The runner puts `src/` on `sys.path` and calls `hocrgen.tools.knesset_lines.main`. The text conversion needs
`soffice`. The tagger runs as `ner_stream.py` in the `heocr-ner` venv (`--ner-python`), offline, on the cached
`dicta-il/dictabert-ner`. It is a filter only.

## Steps and guards (all fail closed)

1. **Plan.** Per term, units are ranked by `sha256("heocr-knessetlines-v1:" + unit_id)`. The first `--per-term`
   (default 8) that are not eval-reserved and have a protocol document are taken. The plenary protocol is the
   enumeration's `protocol_proper` document. The committee protocol is the lowest-id DOC / DOCX whose group type
   contains "פרוטוקול".
2. **Eval reserve (decision 0017).** `refuse_eval_reserved_training_input` runs on the selected units and on the rows.
   Eval and unassigned units are counted and never opened. The packaged registry lists only K1–12 plenary sittings,
   so every K13+ sitting is `unassigned` and refused until heocr-eval assigns it. Committee K16+ units are not
   governed.
3. **Capture.** Only `https://*.knesset.gov.il` URLs are fetched, with at most one request every 3 s and the HeOCR user
   agent. Capture stops at the first 403, 429 or 473, challenge page, other failure or wrong file signature. Every
   request is logged (`capture_log.jsonl`) and every file pinned (`capture_pins.json`).
4. **Input.** The cache is untrusted. A document must match its pin and carry a Word signature, OLE or ZIP. K23+
   serves OOXML under `.doc` names, so either signature is accepted for either extension.
   It is copied into a temp dir and converted with `soffice --convert-to txt` (UTF-8, fresh profile).
5. **Paragraphs.** The `<< דובר >>`-style markers are removed, a paragraph wrapped whole in `<...>` is unwrapped,
   format characters are dropped and whitespace runs become one space.
   - **Front matter.** The masthead, table of contents and agenda go: the body starts at the first speaker heading
     (`היו"ר ...:` or a speaker marker).
   - **Attendance block (committee).** It is kept as lines flagged `in_attendance_block`, cut at that first heading,
     and the gate drops them whole. Its entries, with a list heading on the same line cut off, feed `session_denylist`
     together with `unproven_heading_names`.
6. **Lines.** Each paragraph is wrapped greedily at single spaces, at a width drawn per unit from 40–90 characters
   by seed. A paragraph's lines joined with one space give the paragraph back exactly. A line is dropped for:
   - a private-use or unmapped code point;
   - niqqud (`pointed`);
   - no letter or digit;
   - a leftover marker;
   - any tier-A bidi or digit flag (`bidi_or_digit_flagged`): a wrapped line has no layout to verify.
7. **Privacy.** The tagger runs over `stream_text` of each unit's lines (committee: the lines outside the attendance
   block, the stream `gate_committee_lines` judges). Then the series gate runs. Dropped lines get no row; their text
   goes only to `--private-dir` (default `OUT/private`, never committed). `refuse_ungated_plenary_lines` and
   `refuse_ungated_committee_lines` run before anything is written.
8. **Dedup and cap.** At most 3 lines share one text across the set, then `--max-lines-per-unit` (default 800). Both
   keep lines by sha256 of the line id.

## Output

- `lines_text.jsonl`: one row per line, with these fields:
  - unit: `unit_id`, `knesset`, `sitting`, `date` (committee: `session_date`);
  - position: `paragraph_index`, `line_index`;
  - label: `text`, `wrap_width`, `tier_a_flags`;
  - privacy: `privacy_gate`, `privacy_note`, `is_speaker_heading`, `release_scope`;
  - provenance: `capture`, `label_source`, `reference_eligible`, the document URL and sha256.
- `render_input.jsonl`: `{id, text, group}` for `hocrsyngen render-lines`, with the unit as the group.
- `summary.json`:
  - lines per term and unit;
  - drops by reason and term, with definitions;
  - the gate summary with per-term counts;
  - the dedup counts;
  - the soffice version and the input pins;
  - the eval-reserved check.
- After `render`, hocrsyngen's per-line manifest is joined:
  - `train/<unit>/<id>.png`, each with a logical-order `.gt.txt` holding our text;
  - `manifest.jsonl`, with `face` (the renderer's `font_id`) and `render` (font sha256 and licence, size, weight,
    preset, ink band). This is the shape make_lstmf reads.

  A rendered row is refused when its font licence is not OFL, its image lies outside the render dir, or its gt
  differs from our text.
- `verify` checks the text stage and, when present, the render stage:
  - the eval guard, the gate stamps and the provenance fields;
  - the line rules and the dedup cap;
  - the release scope;
  - png and gt pairing, with no image outside the manifest.
