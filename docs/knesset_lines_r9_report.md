# R9 Knesset training lines: build report (2026-11-13)

This report covers the R9 line sets that `hocrgen.tools.knesset_lines` (see [`knesset_lines.md`](./knesset_lines.md)) builds from born-digital Knesset protocols. It gives line counts per series and term, privacy-gate drops, decontamination drops and per-face size statistics. **No training has run.** R9 is launched through power-scheduler once heocr-eval's mid-century references exist.

- **Requested by:** heocr-lead, 2026-11-13. The plan was approved with gate changes (a), (b) and (c) below, a cap of about 60k + 60k lines, and OFL fonts only.
- **Built by:** `data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource`.
- **Outputs:** workspace only, `tasks/r9-new-printed/{plenary,committee}/out/`. No line text or image is committed here.

## What the lines are

- **Synthetic lines from real text.** Each label is the protocol document's own text (DOC/DOCX, converted by LibreOffice), wrapped into lines by HeOCR and rendered by `hocrsyngen render-lines`.
- **Renderer:** pinned at `32af108112afc51354e398239e7e6376b329b60a` (HeOCR/hocrsyngen#99 and #100).
- **Faces:** 9 OFL-1.1 faces, with font sha256 and licence recorded on every line: Alef, Assistant, David Libre, Frank Ruhl Libre, Heebo, Miriam Libre, Noto Sans Hebrew, Noto Serif Hebrew and Rubik.
  - Decision 0018 as amended 2026-11-13 allows only open-licensed rendering fonts. The maintainer approved the 6 google/fonts additions on 2026-11-13.
  - No system font is used: no Times New Roman, Arial or Calibri.
- **Row fields:** every row records `capture: synthetic_render`, `label_source: born_digital_protocol_text`, `reference_eligible: false` and `eval_use: never`.
- **Size:**
  - Units are split by `sha256("heocr-knessetlines-band:" + unit_id)`. Half render at an ink band of 27–34 px, the IA-like range of the R9 face stats; the other half render at 35–48 px.
  - Weight is drawn from 350–600, clipped to each face's axis.
  - Each unit (a sitting or session) keeps one face, size and weight throughout.
  - The preset is `modern_print_scan_v1` (light).
- **Labels:** `.gt.txt` files are in logical order. r8b's `make_lstmf.py` writes the visual order itself.

## Scope

| Series | Source | Terms | Units planned | Release scope |
|---|---|---|---|---|
| `knessetplenarylines_v1` | Divrei ha-Knesset, born-digital (`knesset_plenary_k13_25`) | K13–25 (1992 on) | 156 sittings (12 per term) | PD-IL §6, publishable |
| `knessetcommitteelines_v1` | committee protocols (`knesset_committee_protocols_k16plus`) | K16–25 (2003 on) | 300 sessions (30 per term) | **training only** (2026-11-11 decision; refused by the release export) |

- **K1–12 plenary scans:** no label route. Their DOC files are Imagestore OCR. Mid-century eval units are all K1–12.
- **Committee protocols from 1976–2003:** not online as text.
- **Eval registry:**
  - Split v6 (`pmod_unit_split_v6.json`, sha256 `2519bc8f…`) holds out 78 K13+ sittings as `holdout_modern_plenary`. They are excluded whole, and their text is also used as a 6-gram target.
  - Split v7 (`de528a4e…`) makes all 44,942 committee sessions non_eval.
  - The builder refuses unassigned units. The registry routes and syncs are heocr-eval's E2f7 PRs, #198 and #200; this PR stacks on them.
- **Unit selection:** seeded by `sha256("heocr-knessetlines-v1:" + unit_id)` per term, over non_eval units only.
  - Plenary: 156 of 156 built.
  - Committee: 296 of 300 built. 4 had no detectable body start and were refused.

## Privacy

**Plenary.** Gate `plenary_private_names_v1`, the 2026-11-13 decision, run with `gate_stream_lines`:
- A name broken across a line end is judged whole, and every physical line it touches is dropped.
- Each line is also judged alone; a line is kept only when both checks keep it.

**Committee.** Gate `committee_private_names_v1`, the plenary gate plus three changes:
- **No structural heading proof.** Guest headings (`<< אורח >>`) and officials marked `<< דובר >>` prove nothing. On 12 test protocols, only 1 of 56 guest speakers and 1 of 6 `דובר` speakers in one protocol were on the roster.
- **A per-session surname denylist,** built from the attendance lists and unproven headings. It overrides a member's matching surname, which is the "מר כהן" witness case.
- **The attendance block** is dropped whole.

**Intake guards.** `refuse_ungated_plenary_lines` and `refuse_ungated_committee_lines` run at intake and in the release export. `refuse_training_only_release` also refuses post-1975 committee rows and images from any release. It is derived from the session date, fails closed when the date is missing, and ignores the scanned pre-1976 committee source.

**Dropped lines.** Their text is written only to `OUT/private/`, workspace only. No committed file names a private person.

| Gate drops | Plenary | Committee |
|---|---|---|
| lines judged | 625,230 | 345,674 |
| dropped | **20,451 (3.3%)** | **52,178 (15.1%)** |
| `not_public` | 17,730 | 30,231 |
| `surname_namesake` | 3,400 | 9,443 |
| `session_denylist` | — | 32,623 |
| `attendance_block` | — | 11,670 |
| `empty_mention` | 108 | 82 |

Lines can carry several reasons, so the reasons add up to more than the dropped lines.

**Gate drops per term** (lines dropped / lines kept):

| K | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plenary | 1,304 / 52,843 | 1,336 / 36,574 | 1,996 / 76,896 | 1,248 / 40,266 | 1,269 / 60,500 | 1,232 / 47,868 | 1,073 / 34,753 | 2,640 / 74,461 | 1,208 / 16,976 | 933 / 22,540 | 1,495 / 36,282 | 1,549 / 36,800 | 3,168 / 68,020 |
| committee | | | | 4,251 / 22,043 | 3,920 / 18,829 | 4,600 / 21,096 | 5,403 / 28,917 | 7,222 / 34,093 | 4,446 / 29,472 | 3,962 / 25,961 | 4,027 / 26,706 | 6,153 / 45,540 | 8,194 / 40,839 |

## Other drops, before rendering

| Drop | Plenary | Committee |
|---|---|---|
| digits or Latin (tier-A bidi flags) | 14,716 | 6,377 |
| no letters or digits | 6,555 | 911 |
| pointed (niqqud) | 439 | 212 |
| leftover speaker markers | 46 | 25 |
| exact duplicates (plenary: over 3 copies; committee, training-only: over 1, safeguard 3) | 127,164 | 60,216 |
| per-unit cap (450 plenary / 240 committee) | 387,884 | 162,872 |

**Rendered:** plenary 68,520 and committee 63,341. No line was refused by the renderer, and `verify` reports 0 problems on both sets.

## Decontamination: a pre-filter, not the official check

- **Tool:** `tasks/r9-new-printed/scripts/decontam.py`. It uses heocr-eval's `check_train_overlap.py` targets as fixed on 2026-11-13: mid-century v1 merged pre-fills, resampled pages and blind pre-fills. It adds one extra pool: the text of the 78 v6 holdout sittings.
- **Comparison:** word 6-grams in logical order.

| 6-gram target | Plenary | Committee |
|---|---|---|
| v6 holdout_modern_plenary sittings (extra) | 3,691 | 363 |
| midcentury_test_pages | 238 | 59 |
| pmod_eval_pages | 36 | 78 |
| wave1 | 20 | 41 |
| rseries_dev_report | 6 | 22 |
| olb_reshumot_dev | 1 | 15 |
| **lines dropped** (a line can hit several targets) | **3,712** | **445** |
| line_verify, tenders, whole-unit paths | 0 | 0 |

- **Holdout overlap:** most of the holdout-sitting overlap is procedural wording that sittings share.
- **Cap:** after the drops, each list is capped to **60,000 lines** by `sha256("heocr-knessetlines-cap:" + line id)`. The plenary cap removes 4,808 lines and the committee cap 2,896.
- **Result:** `check_train_overlap.py` reports CLEAN on both capped lists.
- **The official check is heocr-eval's,** run on the whole composed R9 list (lead, 2026-11-13).

**Final lists:**

| List | Lines | sha256 |
|---|---|---|
| `decontam/plenary_train.clean.list` | 60,000 | `6ce3870d…` |
| `decontam/committee_train.clean.list` | 60,000 | `0512531a…` |
| `decontam/reshumotlines_v2_train.clean2.list` | 70,684 | `03158f39…` (heocr-eval: CLEAN) |

**Final lines per term:**

| K | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| plenary | 4,779 | 4,398 | 4,743 | 4,684 | 4,616 | 4,741 | 4,760 | 4,658 | 4,302 | 4,344 | 4,768 | 4,794 | 4,413 |
| committee | | | | 6,113 | 5,348 | 5,728 | 5,960 | 6,707 | 5,682 | 5,334 | 6,175 | 6,337 | 6,616 |

- **Faces:** each list is balanced over the 9 faces, 5,998–7,084 plenary lines and 6,131–7,518 committee lines per face.
- **Size bands:** plenary 30,143 small / 29,857 large; committee 29,613 / 30,387.

## Per-face size statistics (the R8c per-face balance candidate)

- **Tool:** `tasks/r9-new-printed/face_stats/per_face_stats.py`.
- **IA-like rule:** ink band 27–34 px and ink density ≥ 0.2116. This is Brainin IA's p10–p90 band and p25 density, and it covers 66.7% of IA's own lines.
- **Pool:** R8b `train_main` plus the three lists above, 386,959 lines.

| | R8b main alone | R8b main + Knesset + reshumot v2 |
|---|---|---|
| lines | 196,275 | 386,959 |
| IA-like lines | 51,860 (26.4%) | 95,929 (24.8%) |
| open-ח faces' share of the IA-like range | **20.8%** | **11.3%** |
| open-ח faces' share of all lines | 11.9% | 6.1% |

- **What the new lines add:** 44,069 IA-like lines in 9 modern faces, 4,163–5,502 per face. No face holds more than 5.7% of the IA-like range.
- **The open-ח skew:** it falls by nearly half without removing a line.
- **If R9 also wants open-ח parity** in the range, the stats' targeted proposal applies: thin only the open-ח books' IA-like lines to their overall share. That removes 5,325 lines.
- **A generic per-face cap doesn't help.** A 5% cap removes 1,989 Knesset lines and raises the open-ח share to 11.5%.
- **reshumotlines_v2** contributes no IA-like lines. Its renders are 150 dpi, with a median band of 11 px.

## For the R9 recipe (lead's call)

1. **Do not stack reshumot v1 and v2.** reshumotlines_v2 contains v1's 22,303 surviving rows byte for byte. The R9 list should replace R8b main's reshumotlines_v1 part with `reshumotlines_v2_train.clean2.list`, not add v2 on top. The pool above counts both, so it overstates Reshumot by about 19.5k lines.
2. **Inherited exposure.** heocr-eval reports that R8b `train_main` itself hits 282 lines against today's targets. Drop them, or keep them as exposure shared with the R8b control.
3. **Dose.** 60k + 60k is a ceiling. R9 picks how much to use.
4. **Digit and Latin lines** are dropped, using the same tier-A rule as Reshumot. The renderer shapes bidi correctly from logical text, so they could be kept once someone checks that `make_lstmf`'s visual reordering agrees with libraqm on mixed lines. That's a candidate follow-up.
5. **No language data** may be built from committee text (safeguard 1). Committee lines already keep one copy per exact label (safeguard 3), and every line is a single-line crop (safeguard 2).

— data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource
