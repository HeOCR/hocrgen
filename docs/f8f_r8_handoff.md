# F8f R8 hand-off: real line set `bynli_lines_v3`

On 2026-11-11 the R8 new-printed line set `bynli_lines_v3` was built for heocr-synth-gen under heocr-lead's priority (decision 0018: new printed is the vertical). It holds only units that are **not** in `bynli_lines_v2` (R7). It was built from this PR's branch, hocrgen **93a413f**, which adds alternate-edition support (hocrgen#169) and fixes the multi-work trailer strip.

The full record is [`f8f_r8_handoff.json`](f8f_r8_handoff.json). It has the exact command, the builder summary's key fields, per-book counts, the excluded and dropped lists and the release notices.

Every pair is silver: `human_typed_edition_text_aligned`, `not_adjudicated`, `reference_eligible: false`. The labels are OCR-localised Project Ben-Yehuda edition text, never OCR output.

## Node hints are hints only

Every row carries `proposed_node_hint` (decision 0018), and the summary counts lines by hint and split. **The maintainer's tagger decides each unit's node.** His own first tagging was far stricter than these hints: he placed 22 of 25 units as *old printed*, including Brainin 1928, Artush, Kuzar, Bostenay and Massa ba-Arav; only Silman got new printed. So the `new_printed` counts below are **not settled**.

- The hints come from `f8f_g/proposed_node.json` and `f8f_g/ia_reprobe/proposed_node.json`, unchanged.
- Bachrach, Bodek 1865 and the three f8f_ia stragglers were judged here by look from one cached mid-book page, never by year. Unclear ones are `unclassified`.
- The source tags put `new_printed` on 19th- and early-20th-century book type. They were kept as they are, but they likely overstate new printed:
  - `zikhronotlebetda01reck` (1893) and `zikhronotlevetda01frie` (1904);
  - `sipurim00nombuoft` (1905) and `kolkitveylkatsen018800` (1905);
  - `yotsrehasifrutha00zitr` (1922), `kolkitvereuvenbe11brai` (1922) and `seferhademaotmeo0000bern` (1923).
- `tagger_units.json` in the set lists each of the 20 units with lines. Each entry has the record, title, year, source, split, hint and 2–3 absolute paths to cached full-page scans (not crops). heocr-lead builds the maintainer's tagger set from it.

## Recipe

The recipe is v2's: `--prefer-placer stock --max-lines-per-book 6100`, no `--keep-pointed`. Niqqud is stripped from labels and pointed prints are dropped.

**Roots** (under `real-source-mapping/intermediates/f8f/`):

| Root | What it gives |
|---|---|
| `f8f_g` | f8f_g step 4: 14 IA editions, Korot after its re-run, and `out_alt/` (the Nir David copies and `zikhronotlevetda01frie`) |
| `f8f_g/ia_reprobe` | the 6 f8f_ia books recovered after the probe bug |
| `f8f_r8_lines/roots/f8f_ia_r8` | a symlinked root: `out/` holds the 3 R8 stragglers from `f8f_ia/r8_stragglers/out/`, `out_alt/` holds Hiawatha IA from `f8f_ia/out_alt/`, and `pby` and `work` link to f8f_ia's |
| `f8f_r8_lines/roots/f8f3_r8` | a symlinked root: `out/26111` (Bachrach 1884, round r8) and `out_alt/52535@990010106660205171` (Bodek 1865); `pby` and `work` link to f8f3's |

- The two symlinked roots exist so that none of the 7 R7 f8f3 books or the 26 R7 f8f_ia books can be read. Nothing was moved or written in `f8f3/`, `f8f_ia/` or `f8f_g/`.
- As a second guard, `--exclude-records-from f8f_r8_lines/v2_manifest_records.txt` lists the 33 records with rows in v2.
- `f8f3/r7_sealed/SHA256SUMS` checks clean (28/28) before and after the build.
- **Pointed prints** (named so the builder drops them; no other record has edition text at 0.1 niqqud per letter or more, so the builder asked about none and `--unpointed` was not needed):
  - `ahalrefaimshir00liliuoft`, `dimdumimshirim00katz` and `seferhashirim00hein`;
  - the two Nir David copies `bub_gb_5-Y-AQAAIAAJ` and `nirdavid02coheuoft`;
  - Hiawatha IA, `shirathayaatahme00long_0`.
- **Pointed verse in unpointed prints:** `--drop-pointed-spans` (new) drops a line of a print not named `--pointed` when its edition span carries 0.3 niqqud per letter or more. I applied it to every unpointed record, not only Sefer ha-Dema'ot. Such a line's stripped label would teach a recognizer to drop marks the print may show.
  - It dropped 3,015 lines in 15 records.
  - **Sefer ha-Dema'ot** (`seferhademaotmeo0000bern`) lost 1,273 of them, its fully pointed piyyut verse. It keeps 5,350 lines.
  - The other 14 records lost between 3 and 603 lines each (yotsre 603, zikhronotlebetda 291, kolkitveyl 241, Brainin 205, the rest fewer).
- **Cap:** 6,100 per record. It trimmed six books: yediot 4,037, yotsre 1,934, zikhronotlebetda 1,891, sifruth 1,550, zerubavel 638 and kevar 96.
- **Two scans of one PBY text count as separate books.** The cap is per record, as before: they are different prints. Five Friedberg works (PBY 1959, 2588, 3540, 5521 and 58439) are in train from both `zikhronotlebetda01reck` (1893) and `zikhronotlevetda01frie` (1904).

## Set

| | |
|---|---|
| Lines | 87,452: 81,182 train and 6,270 dev, all unpointed |
| Records with lines | 20: 18 IA and 2 NLI |
| `manifest.jsonl` sha256 | `4cba250f0f3e9207d26fd6e7415b1ed37132123c9c0c9ec961cc58ed0490994e` (verified) |
| Images | written for every row; 0 have a null `image_sha256` |
| IA rows | all 85,120 have `scan_source`, `source_class` and `rights_justification_id`; 0 lack an id. The drops `ia_rights_justification_missing` and `google_hygiene_pending` are both 0 |
| Labels | 0 carry niqqud or cantillation |
| Overlap | 0 records in v2's manifest. `rablines_v1` is not built (`f8f_rab/out` shares no record either) |

**Lines by split and node hint (not settled; see above):**

| Split | old_printed | unclassified | new_printed | Total |
|---|---:|---:|---:|---:|
| train | 30,233 | 22,237 | 28,712 | 81,182 |
| dev | 13 | 0 | 6,257 | 6,270 |

**Train, per book:**

| Record | Year | Source | Hint | Lines |
|---|---|---|---|---:|
| kevarpirezikhron00haco | 1922 | f8f_ia straggler | unclassified | 6,100 |
| sifruthahisoriya11kaha | 1922 | f8f_ia straggler | unclassified | 6,100 |
| yediothateva06bernuoft | 1883 | ia_reprobe | old_printed | 6,100 |
| yotsrehasifrutha00zitr | 1922 | ia_reprobe | new_printed | 6,100 |
| zerubavel00levi | 1901 | f8f_g | old_printed | 6,100 |
| zikhronotlebetda01reck | 1893 | f8f_g | new_printed | 6,100 |
| afahleneemaniml00fngoog (Google) | 1881 | f8f_g | old_printed | 5,751 |
| kolkitveylkatsen018800 | 1905 | ia_reprobe | new_printed | 5,721 |
| seferhademaotmeo0000bern | 1923 | ia_reprobe | new_printed | 5,350 |
| divreyemeolam02schuuoft | 1868 | ia_reprobe | old_printed | 4,668 |
| bioretletoldotha01gott | 1865 | f8f_ia straggler | old_printed | 4,662 |
| zikhronotlevetda01frie | 1904 | f8f_g `out_alt` | new_printed | 4,150 |
| tserorperaimvehu00kovn | 1868 | f8f_g | unclassified | 3,617 |
| mikhtavimmiarsh00mezagoog (Google) | 1886 | f8f_g | unclassified | 3,452 |
| korothayehudimb00friegoog (Google) | 1893 | f8f_g | unclassified | 2,968 |
| 990026910840205171 (Bachrach, NLI) | 1884 | f8f3 r8 | old_printed | 2,319 |
| sipurim00nombuoft | 1905 | f8f_g | new_printed | 1,291 |
| tsitsimuferaimm00geiggoog (Google) | 1856 | f8f_g | old_printed | 633 |

## Dev (held out whole)

| Record | Book | Lines | Hint |
|---|---|---:|---|
| kolkitvereuvenbe11brai | Brainin, collected works (1922) | 6,257 | new_printed (source tag, not settled) |
| 990010106660205171 | Bodek 1865 (NLI, `out_alt`) | 13 | old_printed |
| nirdavid02coheuoft | Nir David 1834 (IA, `out_alt`) | 0 (pointed print) | |
| bub_gb_5-Y-AQAAIAAJ | Nir David 1834 (Google, `out_alt`) | 0 (pointed print) | |

- The v2 dev ids are also passed for consistency: Bodek 1870, `nirdavid01coheuoft`, Silman and Brainin 1928. None of them has rows here.
- **No dev unit is designated new-printed dev.** That role waits for the maintainer's tagging. For example, Brainin's collected works are not new-printed dev unless he says so.
- No PBY text is in both dev and train, in v3 or across v2 and v3. Bodek's PBY 52535 is dev in both sets (1870 in v2, 1865 here).

## Pointed flags

| Record | Print | Basis | In v3 |
|---|---|---|---|
| ahalrefaimshir00liliuoft, dimdumimshirim00katz, seferhashirim00hein | full | `f8f_g/print_pointed.json` | dropped (`--pointed`) |
| bub_gb_5-Y-AQAAIAAJ, nirdavid02coheuoft | full | `f8f_g/print_pointed.json` | dropped (dev) |
| shirathayaatahme00long_0 | full | `f8f_ia/print_pointed.json` | dropped, as expected |
| divreyemeolam02schuuoft, yotsrehasifrutha00zitr | partial (scattered pointed words) | `ia_reprobe/print_pointed.json` | unpointed; pointed spans dropped |
| seferhademaotmeo0000bern | partial (pointed verse in prose) | `ia_reprobe/print_pointed.json` | unpointed; 1,273 pointed spans dropped |
| kevarpirezikhron00haco, sifruthahisoriya11kaha | partial (scattered pointed words) | looked at here: c0112 and c0141 | unpointed; pointed spans dropped |
| bioretletoldotha01gott, Bachrach | none | looked at here: c0120; f8f3 (canvas 71) | unpointed |
| the other 10 | none | `print_pointed.json` | unpointed |

The builder dropped 7,513 lines as `pointed_print` in all.

## Excluded and dropped

- **f8f_g skipped books** (neither direction cleared 2/6):
  - `MN41837ucmf_2`, a microfilm manifest mismatch: 378 canvases against an imagecount of 41, holding another Smolenskin text;
  - `sipurehasidim00stei`, where the record-to-PBY grouping is wrong;
  - `ketavimaaronim00bers`, an OCR miss on its type, still skipped after the blank-page re-probe;
  - `inornaimseferkol02luzzuoft`, a pointed print with no PBY match;
  - `kolkitve00ansk`, which holds The Dybbuk while its PBY works are folk stories;
  - `32882013143071-sipurim`, a pointed children's print with near-blank pages, still skipped after the re-probe.
- **f8f_g near misses not promoted:**
  - the Lilienblum volumes `kolkitvemoshehle04liliuoft`, `kolkitvemoshehle04lili` and `kolkitvemoshehle01lili`;
  - `MN41809ucmf_0`, a microfilm mismatch: 342 canvases against an imagecount of 32.
- **Korot ha-Yehudim bi-Sefarad, resolved.** PBY 52246 and 52613 had been excluded as `justification_publication_place_missing`. They were re-aligned on 925f784 with the saved NLI catalogue snapshot `f8f3/manifests_gate/990012978650205171.json` (sha256 `c67629ba…`), with no NLI request; the images are still the IA scan. Both works are now `rights_justified` and give Korot's 2,968 lines.
- **Microfilm manifest mismatches:** `MN41838ucmf_3` (ia_reprobe) cleared the probe, but all 4 of its works were excluded as `justification_imagecount_inconsistent:42:108`. Like `MN41837ucmf_2` and `MN41809ucmf_0` above, its IIIF manifest serves a whole reel.
- **Yediot ha-Teva, 2 works without a translator death year:** PBY 35732 and 35733 were excluded as `justification_missing_death_year`, because translator פסח רודרמן has no Wikidata QID in the PBY catalogue. The book's other works give its 6,100 lines.
- **f8f_ia re-probe, still skipped:** `givatyerushalayi00wies`, `harimonsipur00brau`, `kolsifreperetsbe06smoluoft` and `32882013393312-kitveyhtavyovke`. These are all single-work books, which the probe bug did not affect.
- **Builder drops:**
  - `label_disagrees_with_line_ocr` 17,962;
  - `pointed_print` 7,513;
  - `below_min_score` 6,918;
  - `pointed_span_in_unpointed_print` 3,015;
  - `outside_repertoire` 1,922;
  - `taller_than_one_line` 1,094;
  - `aligned_twice` 133;
  - `google_watermark_overlap`, `ia_rights_justification_missing` and `google_hygiene_pending`: 0 each.
- **`skipped_alignment_dirs`** lists only the two `out_excluded/out` folders (no `alignment.json`). Every `<pby>@<record>` dir was read.

## Release notices

- **IA scans** (18 records):
  - These are Internet Archive scans of public-domain books, published without an explicit licence. Each item's original IA conditions still apply.
  - The gate is `decide_ia_rights`.
  - Every IA row carries its work's `rights_justification_id` (`planning/decisions/2026-11-10-legal-strategy.md`), so a release can be rebuilt without IA lines and each line points to its justification.
- **Google-digitized IA items:** `afahleneemaniml00fngoog`, `korothayehudimb00friegoog`, `mikhtavimmiarsh00mezagoog` and `tsitsimuferaimm00geiggoog` in train, and `bub_gb_5-Y-AQAAIAAJ` in dev with 0 lines.
  - Each has a hygiene record (`hocrgen.google_hygiene.v1`) in its `rights_justification.hygiene`.
  - For the four train items, canvas 0 (Google's usage-guidelines page) was excluded, and no watermark was found on 249, 316, 412 and 107 pages respectively.
  - `bub_gb_5-Y-AQAAIAAJ` has a watermark box on 218 of 235 pages; any line overlapping one is dropped.
  - Google marks are stripped by rule 5 of the legal strategy.
- **NLI scans** (Bachrach 1884 and Bodek 1865): from the collection of the National Library of Israel (מאוסף הספרייה הלאומית), under the NLI "public domain – free use" terms. Each row's record id leads to its manifest URL and attribution. Bachrach is `990026910840205171`, manifest `https://iiif.nli.org.il/IIIFv21/990026910840205171/manifest`.
- **Text:** the Project Ben-Yehuda public-domain dump, release 2026-03. Credit: "Project Ben-Yehuda volunteers", https://benyehuda.org.

## Still pending

- **f8f3 day 4:**
  - Varshavsky, *Min ha-Moledet* 1919 (`990019041450205171`, PBY 58580), probe-confirmed and not aligned;
  - the 216 NLI groups still pending the gate;
  - the R6 second pass, which waits for gating to finish.
- The maintainer's node tagging of v3's units (`tagger_units.json`). After it, the `new_printed` counts, and any new-printed dev role, can be settled.
- The NLI round's probe (`f8f3/scripts/probe.py`) joined raw files the same way as the f8f_ia probe. It may have the same multi-work false negatives; it has not been re-probed. With this PR, `pby_body` keeps every work of joined text.

— data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource
