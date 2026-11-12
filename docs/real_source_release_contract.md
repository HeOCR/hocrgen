# Real-source release contract and the promoted real tranche (F8g)

`F8g` moves the F8 real sources from `review_only` into the public dataset path, so real printed and handwritten pages, with their human-made text, actually ship. Plan: [`planning/tasks/f8-real-source-map.md`](../planning/tasks/f8-real-source-map.md). Rights: [`planning/decisions/2026-11-06-f8-real-source-decisions.md`](../planning/decisions/2026-11-06-f8-real-source-decisions.md), decisions 1-13.

It has four parts:

1. a **composition contract**, `real_source_composition.v2`;
2. **leakage governance** at the level of works, editions and scan files, with a hook for works that feed synthetic training;
3. **promotion**, with each source's scope markers and attribution carried into every export;
4. a **real tranche**: the full promoted pool, materialized outside git from pinned caches, with a committed manifest.

`F8g2` hardens it: size-aware group splits (§2), the Pinkas canvas checks, the crop height floor, `wikisource_plain_text.v3`, and a tranche v2 that grows Reshumot and the Knesset protocols past their fixtures (§4). `F8e2` rebuilds the Reshumot text from the PDF glyph layer and verifies it line by line, in tranche v3 (§4). `F8e3` makes explicit that only each line is verified, not the order of lines and blocks across the page (`reading_order_verified: within_line`, §3 and §4), keeps such text out of page-order scoring, and retires the `pdftotext` method, in tranche v4.

The same contract shape is meant for `F7d` (HASH).

## 1. Composition contract (`real_source_composition.v2`)

The contract is `src/hocrgen/config/real_source_contract.yaml`, typed by `RealSourceContract`. It replaces the fixed 27 / 27 / 26 NLI / Pinkas / BiblIA allocation in the public-beta `source_depth_composition` gate. The F1 trial keeps its historical allocation (`hocrgen.source_ops.F1_SOURCE_TARGETS`) as an operator-only artifact.

**Counting rules**

- Every gated item ships. The contract counts; it never selects.
- A source's items count toward the real total only up to the source's **cap**. Its **floor** must be met outright. So no one source can fill the target alone: Wikisource's 1,448 shipped pages count as 40.
- The **counted items** of a source are its first `cap` items by item id, so the count does not depend on export order.
- An item's **modality** comes from its declared `content_type`, else its classified `content_class`. A `mixed` item has no modality: it counts toward the total, never toward a modality floor.
- A source with `counts_toward_modality_floors: false` counts toward the total only. Reshumot is one: its pages are rendered from born-digital PDFs, not scanned.

**The gate passes only when all of these hold**

- every source floor is met;
- the printed and handwritten floors (the E2d tracks) are met by counted items;
- the counted total reaches `min_real_items` (80);
- no real item comes from a source outside the contract, or from a `not_promoted` entry;
- no `f1_source_depth_only` item reached the payload;
- `source_stats` matches the payload.

| Source | Promotion | Modality | Floor | Cap | Release terms |
| --- | --- | --- | --- | --- | --- |
| `wikisource_he_proofread` | promoted (F8g) | printed | 20 | 40 | CC BY-SA 4.0, attribution and share-alike; full Hebrew; page text ships |
| `yidtaknl_vaybertaytsh_gt` | promoted (F8g) | printed | 5 | 15 | CC BY 4.0, attribution; `character_level_only` (decision 6); page text ships |
| `pinkas_dataset_bgu` | promoted (F8g) | handwritten | 10 | 30 | CC BY 4.0, attribution; per-line scope (decision 8); PAGE XML ships |
| `nli_any_use_permitted` | legacy (F8c printed books) | both | 0 | 20 | PD-IL; images only |
| `reshumot_born_digital` | promoted (F8g) | printed, not counted toward the modality floors | 0 | 5 | PD-IL; `rendered_not_scan`; page text ships, `reading_order_verified: within_line` (F8e3) |
| `knesset_committee_protocols_pre1976` | promoted (F8g) | printed | 0 | 10 | PD-IL; images only |
| `pinkas_open`, `biblia_open` | legacy | handwritten | 0 | 15 each | PD-IL; images only |
| `hash_nli_any_use`, `hash_public_domain` | not promoted (F7d) | handwritten | 0 | 40 / 20 | F7d sets the promotion and a floor; nothing else changes |

Modality floors are printed 30 and handwritten 25. The handwritten floor is what the 30 BGU Pinkas pages can meet today; `F7d`'s HASH tranche is the way to raise it.

**The legacy floors are 0.** This is a deliberate change from 27 / 27 / 26. NLI, `pinkas_open` and `biblia_open` ship images with no text, so they do not help a real-scan reference set; their F1c operator inventory was never countable anyway.

**Load-time checks**

- `RealSourceContract` rejects contracts that cannot be met or do not hang together:
  - a floor above its cap;
  - a floor on a `not_promoted` entry;
  - floors whose sum exceeds the total;
  - a modality floor or the total that the caps cannot reach;
  - one content type mapped to two modalities;
  - share-alike without attribution.
- `validate_real_source_contract` binds the contract to `sources.yaml`:
  - every entry names a registered source;
  - promoted and legacy entries are `allowed` and default-public;
  - not-promoted entries are not;
  - the licence agrees with the source's `normalized_license`;
  - every `allowed` real source in any profile has an entry, so a source cannot reach the public path outside the contract.

The report is `manifests/public_beta_source_depth_composition_report.json`, schema 2, planning notation `F8g`. It lists per source the floor, cap, payload count, counted count and modality counts; per modality the floor and counted count; and every gap. The dataset card has a **Real Source Composition** section.

## 2. Leakage governance

**Source groups**, which already existed and are unchanged, keep one source's pages of one work together:

- one Wikisource Index (one Commons file);
- one YidTakNL work (one printed edition);
- the BGU Pinkas manuscript, NLI Ms. Heb. 4°662;
- one Reshumot booklet;
- one Knesset protocol.

**Work groups** (`hocrgen.split.work_groups`) tie items of different sources that show the same edition, scan or writer:

- `nli_record:<id>`: one NLI record, which covers an NLI seed, the YidTakNL pages and the BGU Pinkas pages matched to its canvases;
- `commons_file:<sha1>`: one Commons scan file;
- `writer:<id>`: one HASH writer group.

**Split assignment** (`hocrgen.split.assign`) now joins items through every grouping into connected components: exact-duplicate clusters, near-duplicate clusters, source groups and work groups. A whole component lands in one split.

- A component's split-group id is the smallest F1d split-group id among its members.
- **Which split a component gets is size-aware (F8g2).** F8g hashed each component to a split on its own, which ignores size: with few, unequal groups the tranche came out 65 / 34 / 1.5% against 80 / 10 / 10, with every Pinkas and YidTakNL page in train. The split stage now calls `hocrgen.split.balance.assign_group_splits`, algorithm `size_aware_group_split.v1`:
  1. Components are balanced per **stratum**, `<source_id>:<content type>` of most of their items, so each source and modality approaches the policy on its own.
  2. In a stratum of `N` items, split `s` targets `ratio_s × N` items. The largest split (`train`) is the sink; the holdouts fill in the order `test`, `validation`.
  3. **Pinned** components take their split first and count toward it: a benchmark item's committed `benchmark_split` (read from the benchmark config, so `benchmark_v1` never moves), and a synthetic-training overlap (train). A component holding an evaluation-reserved unit is pinned to `eval_reserved`, outside the policy, and leaves its stratum before placement (see *Evaluation-reserved units* below).
  4. The other components are visited in seeded order, ascending `sha256(seed + "\0" + component id)` (seed `hocrgen-split-v1`). The order of one component does not depend on the others.
  5. A component of `n` items enters a holdout only if it fits, `count + n ≤ target + 0.5` (the target rounded to the nearest item); among the holdouts it fits, it takes the one with the largest share still open. Otherwise it goes to train.
- Consequences: a group never splits, and a group larger than a holdout's target never goes there, so a one-group stratum (the BGU Pinkas manuscript) stays in train; a stratum too small for half an item in a holdout puts nothing there; with many small groups each holdout is met to within one item. A pool change moves only components visited after it whose fit changes: on the Wikisource pool (58 Indexes, 1,455 pages), dropping one Index moves 13 of the other pages at the median and 3% on average.
- **Reference constraints (`size_aware_group_split.v2`, E2d3e, team-lead decision 2026-11-07).** Item counts alone left the release `test` split holding a single book's adjudicated Wikisource pages (three pages after E2d3d). So each component now carries a **reference weight**: the characters of exactly the pages the real printed evaluation scores, on the text it scores (`scored_reference_characters`). Those are adjudication-eligible quality-4 pages and pages scored on their validating-revision text (E2d3b/E2d3c), after every page gate. The fetcher and `wikisource_eval_references` both call `fetchers.wikisource.scored_page_reference`, and a test checks that the two page sets are equal. In a stratum with any reference weight, `test` must hold:
  - at least **2** weighted components (`min_groups`): a held-out result from one book is a one-book result, and the book bootstrap needs two clusters;
  - at least **10%** of the stratum's reference weight (`min_share`), the test ratio of the split policy;
  - no single component above **50%** of the test split's reference weight (`max_group_share`): no book holds a majority of test's adjudicated text.

  When `test` fails, every weighted component keeps the split it was placed in. Test then takes one more weighted component from train, one that would not itself exceed the cap. Every eligible component is tried, and the free (unweighted) components refill around it. The algorithm prefers a component whose move alone satisfies the constraint, then the fewest items, then the smallest weight, then the seeded order. This repeats until the constraint holds; a constraint that cannot be met is reported, never forced. Moved items record `split_constraint: reference_constraint`. A stratum without reference weight is placed exactly as in v1. `validation` is not constrained (team-lead decision): it is too small to tune on, so tuning stays on synthetic validation, and it is reported only as a labelled diagnostic, together with test.
  - **On tranche v5.** Test held Hebrewbooks 19784, *Sefer ha-Mispar* and Hebrewbooks 38168: 8.6% of the scored characters, with Hebrewbooks 19784 at 78% of them. It failed `min_share` and the cap.
  - *Dorot ha-Rishonim* I, *Hut ha-Meshulash*, *Masa ba-Arav* and Hyman I would each hold more than 50% of test by themselves, so none is eligible.
  - *Artush* and Hyman III would leave Hebrewbooks 19784 above 50%.
  - ***The Selihot for the Entire Year*** (59 pages) is the eligible book whose move clears the constraint. Afterwards test holds 15.4% of the weight, and its largest book 43.8%.
- The leakage report's `split_assignment` block gives the algorithm, seed, policy and per-stratum item and group counts. For a weighted stratum, it also gives each split's reference weight and largest component, the constraint moves and any unmet constraint. The function is pure (`SplitGroup` in, split per group out), so other tools can place their own groups the same way: the E2d2 real printed reference pool, for example, can call it on its Indexes.
- The leakage report adds `work_group_leaks` and `synthetic_training_overlap`. A leak of either kind fails the split stage, as before.

**Benchmark and holdout (F1e)**

- The F1e leakage artifact adds `work_group` risks: a benchmark item sharing a work group with a non-benchmark item.
- It also adds `synthetic_training_work` risks: a benchmark item whose work feeds synthetic training. This kind has no accepted resolution. Such an item must leave the benchmark through a membership change.

**Synthetic-training cross-check**

- `HeOCR/hocrsyngen` plans Project Ben-Yehuda public-domain text as recognizer training text (S15a, `HeOCR/hocrsyngen#90`). Each corpus build will publish a work-level exclusion list. `hletterscriptgen` already crops glyphs from HASH scans (F7).
- The registry `src/hocrgen/config/synthetic_training_works.yaml` (`synthetic_training_works.v1`) records such works, each with the work-group keys of the real items that show it. For example, the `nli_record` keys that `F8f` matched PBY editions to.
- A real item that matches a registered work stays in `train` with its whole component. Its split assignment says `split_constraint: synthetic_training_overlap`.
- The registry is packaged with its two producers and **no works**, because no S15a corpus has been built yet.
- The n-gram overlap check that S15a also asks hocrgen to run (real references against the corpus line index) is `hocrgen.tools.eval_text_leakage` (`E2d2`, [results](./e2d2_real_printed_evaluation.md#leakage)).

### Evaluation-reserved units (decision 0017)

heocr-engine decision 0017 (`HeOCR/heocr-engine#74`) splits evaluation by domain; heocr-eval owns printed-modern (P-mod). Its split file, `pmod_unit_split_v<N>.json`, lists for Reshumot and the Knesset protocols the **units** (one Reshumot booklet, `reshumot:<series>_<number>`; one Knesset protocol, `knesset_protocol:<document id>`) that are `eval` and those that are `non_eval`. Its usage rule: eval units are never used for training, tuning, selection, glyph harvesting or synthetic style or layout sources; non-eval units are open; a unit in neither list is **unassigned** and is used for neither until a new version assigns it.

- **The registry** is `src/hocrgen/config/eval_reserved_units.yaml` (`eval_reserved_units.v1`, typed by `EvalReservedUnitsRegistry`). `python -m hocrgen.tools.eval_reserved_units sync --split <file>` generates it, never a hand edit. It copies the split file verbatim to `src/hocrgen/data/eval/`. It records the file's name, version and sha256, the schema the file states, the decision, the owner, the usage rule and its unassigned sentence verbatim, and each source's eval and non-eval units. A test re-renders the registry from the committed copy and fails on any difference (`check` does the same). Each unit's category comes straight from the file: v1's `status: exposed` marks two booklets that left eval for good (they were used in R4f dev selection); they are `non_eval`, so they are open.
  - **Today: v5** (sha256 `873cef9c…c8a45`, `split_version` `v5`). It supersedes v4 and changes only `reshumot_scanned`, from heocr-eval's `midcentury_unit_split_v2` (sha256 `fd9f5717…`): the 5 queue units that gave layer-exact dev lines (kovetz_hatakanot 592, 695, 648 and 555 for 1948-59, 2719 for the 1970s) become `dev`, and the 35 unused queue units return to non-eval, giving 125 eval and 8,086 non-eval.
  - **v4** (sha256 `c641b1e3…d3a21a5`, `split_version` `v4`). It supersedes v3 and changes only `reshumot_scanned`, re-derived from heocr-eval's `midcentury_unit_split_v1` (sha256 `f9a49238…`): the 5 mid-century dev units with no layer-exact OLB dev line are `dev_retired` (still eval), and a 40-booklet dev replacement queue (`dev_queue`, kovetz_hatakanot 1948-59 and 1970s) moves from non-eval to eval, giving 160 eval and 8,051 non-eval. Queue units that turn out unused are released by a later version. Pre-1957 kovetz_hatakanot booklets have no text layer, so the layer-only dev rule cannot cover them.
  - **v3** (sha256 `36ab37e6…3dad6d95`, `schema_version` `heocr_eval_unit_split.v1`, `split_version` `v3`). It supersedes v2 (sha256 `a75ed685…25be7`), copying its born-digital and committee assignments unchanged, and adds the mid-century scanned sources from heocr-eval's `midcentury_unit_split_v0` (sha256 `d62f8ecc…`): `reshumot_scanned` (8,211 ספר החוקים and קובץ התקנות booklets, 1948 to mid-2005; 120 eval = 60 test + 60 dev, 8,091 non-eval) and `knesset_plenary_k1_12` (5,338 sittings; 60 eval = 30 test + 30 dev, 5,278 non-eval). Every enumerated unit is listed, so none is unassigned. Born-digital Reshumot: 30 eval and 175 non-eval. Knesset committee: 7 and 13. v2 had added the 121 born-digital 2005 booklets to v1, and v1 (sha256 `184d3b77…562e`) is the origin.
- **Unit ids** (`hocrgen.split.eval_reserved`). An item's unit comes from the fetchers' metadata (`reshumot_series` and `reshumot_booklet_number`; `knesset_document_id`), else from its ids: the source group (`reshumot:<series>:<n>`, `knesset_committee:<id>`) and the page, entry or item id (`[reshumot_born_digital:]<series>_<n>__p0001`, the R4f form `reshumot_<series>_<n>__p0001`, `[knesset_committee_protocols_pre1976:]knesset_committee_<id>__p0001`). A test maps all 1,003 Reshumot and Knesset items of the committed tranche manifest. Ids that name two units are refused.
- **Scanned Reshumot and Knesset plenary (`E2f2`, decisions 0017/0018).** Two more sources are governed.
  - `reshumot_scanned`: one scanned Reshumot booklet. It has its **own unit prefix**, `reshumot_scanned:<series>_<n>`, with the born-digital series strings (`sefer_hachukim`, `kovetz_hatakanot`). Its page and item ids are `[reshumot_scanned:]reshumot_scanned_<series>_<n>__p0001`, and its source group is `reshumot_scanned:<series>:<n>`.
  - `knesset_plenary_k1_12`: one plenary sitting, `plenary:K<knesset>_<sitting>` (for example `plenary:K1_1`). Its page and item ids are `[knesset_plenary_k1_12:]plenary_K<knesset>_<sitting>__p0001`.
  - No new id shape matches a born-digital or committee pattern, and those patterns are unchanged. Every id therefore names one source.
  - **One booklet, one source.** The registry fails validation when a `(series, number)` appears in both `reshumot_born_digital` and `reshumot_scanned`, in any category.
  - **Fail closed.** An id that only *looks* like a scanned-Reshumot or plenary id (it starts `reshumot_scanned`, `plenary:` or `plenary_`, in any case) but matches no pattern governs its row with no unit, so the row is refused.
  - **Until the split lists them.** Neither `pmod_unit_split_v1` nor `pmod_unit_split_v2` lists these sources; v2 adds only the 121 born-digital 2005 booklets, all non_eval (`E2f3`). Until then, every scanned-Reshumot and plenary row is `unassigned` and refused. `sync` already accepts split files that list them. `pmod_unit_split_v3` will add them once their enumeration and the mid-century split exist, and will be synced as `E2f4`.
- **The release split** pins every component that holds an eval or unassigned unit to a dedicated holdout, **`eval_reserved`**, before balancing. It is not `test`: `test` has its own meaning and sizing (the policy ratio and the reference constraints), and eval units are held for heocr-eval's P-mod set, not the release holdout. So:
  - `eval_reserved` is outside the split policy. Its components are taken out of their stratum before the item placement, so the other components of the stratum are balanced over train, validation and test as before;
  - a whole component moves: a non-eval page joined to an eval page (a duplicate, say) goes with it;
  - a component that also matches a synthetic-training work (train) or a committed benchmark split fails the split stage: no pin wins silently;
  - moved items record `split_constraint: eval_reserved_unit`;
  - the items ship in `data/eval_reserved/`, labelled, with their release terms.
- **The leakage report** adds `eval_reserved_units`: the registry and split file, item and unit counts per status and source, the reserved units present, the items carried with them, and `leak_item_ids`. A reserved item outside `eval_reserved` fails the split stage. `split_assignment` reports `eval_reserved` items and groups per stratum, outside the policy shares.
- **Fail-closed refusal.** `copy_export_assets` (the shared export of `export-alpha`, `export-public-beta` and the heocrsynth export) refuses a reserved item in any other split. Every training-input builder passes its input through `refuse_eval_reserved_training_input` before it writes anything: `benyehuda_nli_lines build` (the selected line rows), `wikisource_lines build` (the snapshot pages), `glyph_harvest` (every style source and every unit, at `harvest` and `write_bank`), and `reshumot_lines build` (the selected Reshumot pages and the line rows; it reads only `non_eval` booklets and never opens the others, see [`reshumot_lines.md`](./reshumot_lines.md)). The guard raises `EvalReservedUnitError`, naming the builder, the decision, the registry's split file and each refused unit with its status. A row is governed when its source is Reshumot or Knesset, or when any of its ids has a Reshumot or Knesset shape, whatever source it names; a governed row whose unit cannot be derived is unassigned. Of these builders only `reshumot_lines` reads those sources; for the others the guard changes no output, and tests feed it synthetic rows.
- **On tranche v5** (the split stage replayed offline on the v5 public-beta run's release-ready items; metadata only). The replay without the pin reproduces the stored v5 split of every Reshumot and Knesset item. With it:
  - **all 37 eval units (281 pages) move to `eval_reserved`**: 230 pages from train, 30 from validation, 21 from test. Reshumot: 30 booklets, 241 pages. Knesset: 7 protocols, 40 pages. From test: protocols 399388, 430997 and 631370 and booklet sefer_hachukim_2315. From validation: protocols 398637 and 635525 and booklets kovetz_hatakanot_6810 and 7282 and sefer_hachukim_2748. The other 28 came from train;
  - no unit of the tranche is unassigned, and no other item is carried with an eval unit;
  - the strata shrink, so 11 of the 67 non-eval units (88 pages) are placed anew among train, validation and test; the other 56 keep their split;
  - Reshumot becomes 444 / 56 / 56 pages (train / validation / test), against 637 / 80 / 80 before, and Knesset 133 / 17 / 15 against 164 / 21 / 20. The readiness table below is the 2026-11-07 run, before the pin.

## 3. Promotion and release terms

**Config changes**

- `wikisource_he_proofread`, `yidtaknl_vaybertaytsh_gt`, `pinkas_dataset_bgu`, `reshumot_born_digital` and `knesset_committee_protocols_pre1976` are now `status: allowed`, `default_public_release: true`, and in `profile_open_v1`.
- `nli_any_use_permitted` was already allowed. Its three cached F8c printed books (`nli-pb-001`–`003`) move from the exploratory catalog to the runnable seeds. The F1 NLI depth count becomes 30, and the F1 allocation is unchanged.
- `wikisource_he_proofread` drops `requires_manual_review`. That review covered the agent-recorded rights evidence, which is now committed (`docs/wikisource_index_evidence.json`) and replayed by a test through the unchanged gate.

Every gate, validator and exclusion reason is otherwise unchanged.

**Release terms per item.** Every exported item in `export-alpha` and `export-public-beta` carries typed `release_terms` (`ItemReleaseTermsRecord`), built from its own metadata and checked against its source's contract terms:

- licence and rights classification;
- `attribution_required` and `attribution_text` (each Wikisource item names its pinned page permalink);
- `share_alike`;
- `text_licence`;
- `evaluation_scope`, `allowed_uses` and `excluded_evaluations`;
- the Pinkas `line_scope_summary`;
- `rendered_not_scan`;
- `reading_order_verified` (F8e3), when the contract names it. Reshumot is `within_line`: each line's text is verified, the order of lines and blocks across the page is not. Such an item also lists `page_reading_order` in `excluded_evaluations`.

An item that cannot carry its source's terms stops the export. For example, a YidTakNL item without `character_level_only`, or without both of its exclusions, or a Reshumot page without `is_scan: false` or without `reading_order_verified: within_line`.

**Paired text.** The human-made text ships next to the image, in `data/<split>/<item_id>/`, checked against the checksum its snapshot pinned:

- `page_text.txt` for Wikisource, YidTakNL and Reshumot;
- `page.xml`, decompressed, for BGU Pinkas.

The item lists its texts in `exported_texts`.

**NOTICE and attribution.** Each export writes `docs/NOTICE.md` and `manifests/attribution_manifest.json` (`hocrgen_attribution_manifest.v1`). For each source they give:

- the licences, and whether attribution is required;
- share-alike, the evaluation scopes, and the count of rendered (not scanned) items;
- the contract's notice text;
- every item that needs attribution, with its attribution text.

The public-beta docs gate requires `docs/NOTICE.md`.

## 4. The real tranche

The full pool (tranche v5, `e2d3e_real_tranche_v5`) is 2,608 pages and 1,032 MB. It never enters git. `python -m hocrgen.tools.real_tranche` builds it reproducibly in an operator folder:

```bash
# 1. capture what no operator cache holds yet (network; each file checked against the pin the repo already records)
PYTHONPATH=src python -m hocrgen.tools.real_tranche capture --cache <cache> \
  [--source yidtaknl|pinkas|reshumot|knesset ...] [--pinkas-manifest-copy <F8d2 copy of the NLI manifest>] \
  [--reshumot-per-query 2] [--knesset-per-term 3]
# 2. materialize the tree from the caches (offline; the Wikisource API cache is replayed, and any miss fails; poppler)
PYTHONPATH=src python -m hocrgen.tools.real_tranche materialize --out <tranche>/f8e3_real_tranche_v4 --cache <cache> \
  --wikisource-work-dir <F8b7 inventory work dir> --wikisource-renders <renders dir> [--wikisource-renders ...] \
  --created-at 2026-11-07 --manifest-out src/hocrgen/data/real_tranche
# 3. check every file, and build or export against the tranche (only a tree that matches the committed manifest is accepted)
PYTHONPATH=src python -m hocrgen.tools.real_tranche verify --tranche <tranche>/f8e3_real_tranche_v4
PYTHONPATH=src python -m hocrgen export-public-beta --profile profile_open_v1 --dry-run --real-tranche-root <tranche>/f8e3_real_tranche_v4 ...
# E2d3e: a tranche with the committed Wikisource page checks re-applied, and each page's pinned validating revision
# and committed validated-text check carried (offline; only pages a newer check excludes are dropped). Tranche v5 is
# v4 refreshed this way.
PYTHONPATH=src python -m hocrgen.tools.real_tranche refresh-wikisource --base <tranche>/f8e3_real_tranche_v4 \
  --out <tranche>/e2d3e_real_tranche_v5 --created-at 2026-11-07 --validated-revisions <wikisource_validated_revisions output> \
  --validated-text-checks docs/wikisource_validated_text_checks.json --manifest-out src/hocrgen/data/real_tranche
# F8e2 / F8e3: a tranche with only the Reshumot snapshot rebuilt (poppler and pdfminer.six: pip install '.[pdf]').
# Tranche v3 was v2 refreshed (F8e2); tranche v4 is v3 refreshed (F8e3).
PYTHONPATH=src python -m hocrgen.tools.real_tranche refresh-reshumot --base <tranche>/f8e2_real_tranche_v3 \
  --out <tranche>/f8e3_real_tranche_v4 --cache <cache> --created-at 2026-11-07 --government-print-captured-at 2026-11-07 \
  [--reshumot-glyph-layers <layers extracted before>] [--reshumot-report <pages.jsonl>] --manifest-out src/hocrgen/data/real_tranche
```

**What is captured, and how it is checked**

- **YidTakNL:** the 121 matched pages with text, from the dataset's public SURFdrive share. Each is checked against the share's SHA-1 and byte count in `matched_pages.jsonl`.
- **BGU Pinkas:** the zip from Zenodo, checked against its MD5. The NLI manifest is checked against the pinned capture's upstream sha256.
- **Reshumot (F8g2):** one gazette search per series (ספר החוקים, קובץ התקנות) and Hebrew year from 2006, and the PDFs of a seeded sample of booklets of at most 24 pages (2 per search), 4 s apart, with the public client id. Each PDF's sha256 is recorded in the cache listing and pinned by every entry.
- **Knesset (F8g2):** per Knesset term 1-8, one OData count and one page of protocol PDFs at a seeded offset (sessions up to 1975-12-31), then a seeded sample of open-session protocols, at most one per committee, 15 s apart. 34 Knesset requests in all; nothing was blocked.

**What the tree holds**

- `tranche.json` and `SHA256SUMS`.
- `sources/<source_id>/snapshot/` in each fetcher's own packaged snapshot format. The unchanged fetchers and gates read it.
- **Wikisource:** every page the F8b6 inventory passed, rebuilt from its API cache with the committed agent and tool checks. The images are the 960 px Commons renders, unchanged. Each partial page has its crop.
- **Wikisource text is `wikisource_plain_text.v3` (F8g2, #134).** The version now covers the F8b7 changes (the dropped note-list headings; unprinted notes dropped by reviewed checks), and v3 renders the label of a broken link as the page prints it: a doubled pipe (Hyman I p. 44), an unclosed link (Hyman II p. 239) and two unopened links (Hyman I p. 414, *Sefer Arakhim* p. 11), each checked on the page render and against MediaWiki's own `action=parse` rendering (which shows the fragment literally). Only those 4 of the 1,455 pair texts change. The fifth `|` fragment (Pri Megadim p. 244) is no link: the editor typed the expansion `"הלכות פסח|` where the page prints the abbreviation ה"פ, so that page is `text_not_on_page`. Each item's metadata carries `text_derivation`: the converter version, its repairs, the unprinted notes dropped and the stand-in mappings applied.
- **YidTakNL and Pinkas:** the upstream images and texts, unchanged. Each Pinkas entry carries `scan.match_check` from `docs/pinkas_canvas_match_checks.json` (below).
- **Reshumot (F8e2):** every page of every captured booklet. Each page's text is rebuilt from its glyph layer (`pdf_glyph_geometry_logical.v1`, see `planning/tasks/f8-real-source-map.md`, F8e2 findings), and every line is verified against the page's `pdftoppm` 150 dpi gray render (`is_scan: false`). Lines that cannot be verified are left out, and the pair image is cut to the verified regions (decision 12; `crop.method: pdf_glyph_regions.v1`). The gate re-derives every page from the committed glyph layer (`extraction/*.glyphs.json.gz`), the outline identity table (`glyph_outlines.json`) and the render.
  - **Reading order (F8e3).** What is verified is each line's text: its characters and their order inside the line. The order of lines and blocks across the page follows a layout convention (body lines top to bottom, side headings before the body line beside them, narrower blocks read whole) and is not verified. A side heading level with a body line may be joined to it or read after it, and table cells may be read row by row or column by column. Every entry records `text.reading_order_verified: within_line`, and the gate refuses an entry that records anything else (`reading_order_scope_mismatch`). The fact reaches item metadata, the committed manifest items and the release terms.
  - **Evaluation constraint (F8e3).** Between-block order differences in this text are not recognition errors. An evaluation that scores it must use the `line_matched.v1` view of `hocrgen evaluate-references` and never a page-order CER. A reference or unreviewed text built from it must declare `reading_order_verified: within_line`; it is then left out of every page-order aggregate (see [`reference_evaluation.md`](./reference_evaluation.md)). The text is still `not_adjudicated`, so no Reshumot page is scored today.
  - **One method.** F8e's `pdftotext` method (`poppler_bidi_logical.v1`) is retired. The packaged fixture uses the glyph layer too, and the gate refuses any other normalization (`unsupported_text_normalization`).
- **Knesset:** every page of every captured protocol that is one embedded scan, extracted losslessly with `pdfimages`: the 1-bit CCITT scans as PNG, and the colour rescans' JPEG streams byte for byte. Images only.
- The packaged fixture's admitted Reshumot and Knesset pages are kept as packaged.

**The committed manifest** is `src/hocrgen/data/real_tranche/tranche_manifest.json` and `tranche_items.jsonl`. It holds no page text. It records:

- per item: the source, id, source group, modality, asset checksum and size, text checksum, crop flag and upstream provenance, and for Reshumot `reading_order_verified` (F8e3);
- per source: the checksums of the snapshot's descriptor files;
- the digest of `SHA256SUMS`.

**Using the tree.** `--real-tranche-root` on the pipeline commands checks the tree against the manifest, then points each tranche source at its snapshot. Every other source keeps its packaged fixture snapshot. Source health writes `tranche://` paths, so no absolute local path reaches an export.

| Source | Pages in the tranche | Groups | Bytes | Left out |
| --- | --- | --- | --- | --- |
| `wikisource_he_proofread` | 1,452 (1,212 full pages, 240 crops) | 58 Indexes | 631 MB | 4 pages `text_not_on_page` (Pri Megadim p. 244, F8g2; Hebrewbooks 19784 pp. 8, 24 and 25, E2d3c/E2d3d, dropped in v5) |
| `yidtaknl_vaybertaytsh_gt` | 123 (121 matched pages, plus the 2 vendored 1781 pages) | 3 works | 164 MB | 33 matched pages whose upstream text file is empty (below) |
| `pinkas_dataset_bgu` | 30 (24 train, 6 test upstream) | 1 manuscript | 49 MB | none |
| `reshumot_born_digital` | 798 (796 captured, 275 of them cropped; 2 fixture, glyph layer since F8e3) | 84 booklets | 141 MB | 90 of 886 captured pages (below) |
| `knesset_committee_protocols_pre1976` | 205 (202 captured, 3 fixture) | 20 protocols | 46 MB | none |

NLI keeps its packaged snapshot (10 items); its image server answered HTTP 520 throughout.

**Pass rates of the new captures (F8g2, 2026-11-07)**

- **Reshumot:** 84 booklets, 886 pages (2 more PDFs answered HTTP 500). Under F8g2's `pdftotext` method 180 pages passed (20%), and none from 2017 on. Under F8e2's glyph-layer method **796 pass (90%)**: ספר החוקים 479 / 508, קובץ התקנות 317 / 378, and 2017-2026 243 / 272. The 90 left out lack a verifiable anchor (no running footer, an API booklet number, date or title that differs from the print, an anchor line overlapping a stamp), have nothing verifiable to keep, or fail the unchanged order heuristics.
- **Knesset:** 18 protocols (Knesset 1-8, sessions 1949-06-29 to 1974-12-24, 16 committees), 202 pages, all pass. 23 pages come from three colour rescans (JPEG); the rest are 1-bit CCITT scans.

**YidTakNL pages with empty text.** The 33 matched pages left out have no text upstream; it is not a parsing problem. F8g2 fetched all 33 `.txt` files again from the SURFdrive WebDAV share: each answered HTTP 200 with 0 bytes, and the share lists each with SHA-1 `da39a3ee…` (the SHA-1 of nothing). The share holds no other text format (only `*.jpg` and `txt/*.txt`). An agent looked at their images: 29 are covers, marbled endpapers or blank leaves, and 4 (JB 899 pp. 100, 102, 110, 128) carry only mirrored show-through of the facing print, so the transcribers had nothing to transcribe.

**BGU Pinkas canvas checks.** The binding of each dataset page to its NLI canvas (the F8d2 label rule: `Page N_1` is the right half, `Page N_2` the left half of canvas "Page N") is now checked per page in `docs/pinkas_canvas_match_checks.json` (`hocrgen.pinkas_canvas_match_checks.v1`):

- **6 pages verified, no mismatch:** Pages 105, 112 and 134, both halves. An agent compared each cached NLI canvas image (1,200 px, cached by F8d2) with the dataset's two halves side by side: the same text blocks, marginal and folio numbers, ink blots, stains and paper edges.
- **24 pages not verified:** no cache holds their canvas images, and the NLI IIIF server answered HTTP 520 on 2026-11-07 (its other hosts answer 403 to scripts). Each records `status: not_verified` and why; the entry's `match_method` says so, and `scan_match_check` reaches item metadata. The checked pages span the manuscript's range (105-134), which supports the rule, but the other 24 wait for the server.

### Hosting proposal (maintainer decision; nothing has been published or uploaded)

The tree (v2) is about 910 MB in 5,689 files: JPEG and PNG images, UTF-8 text, PAGE XML and JSON. The licences are mixed, CC BY-SA 4.0, CC BY 4.0 and PD-IL, per item.

| Route | For | Against |
| --- | --- | --- |
| **Zenodo record** (versioned, with a DOI) | Immutable, citable versions. 50 GB per record. The DOI and the file checksums can go into `tranche_manifest.json`, so `capture` can fetch the whole tree and check it. CERN-run, built for long-term archiving. | Each change is a new version, which is slow for iterating. The record carries one licence field, so the mixed licences need the description and NOTICE. No browsing or streaming. |
| **Hugging Face dataset repo** (an `HeOCR` org) | Already a `profile_open_v1` publish target. Xet/LFS-backed, revisions and tags, a dataset viewer, `datasets` loading. Handles mixed licences in the card. | A hosted platform under its own terms. Large binary churn makes history heavy. A good fit for the release payload, less so for a raw source snapshot. |
| **GitHub release assets** on `HeOCR/hocrgen` | Tied to a hocrgen tag. No new account. 2 GB per file, so one tarball fits. | Not a data platform: no browsing or per-file access. Bandwidth and retention are not guaranteed for datasets. |
| **Git LFS** in a data repo | Reviewable pointers next to the manifest. | GitHub LFS storage and bandwidth quotas: every clone pulls GBs, and the cost grows with each version. Not recommended. |

**Recommendation**

- Archive each tranche version on **Zenodo**, with the DOI recorded in the committed manifest, as the reproducible source of the real pool.
- Publish release exports (the public-beta payload, once every gate passes) to the **Hugging Face** dataset repo already named as a publish target.

Both routes carry `NOTICE.md` and the attribution manifest. Share-alike for the Wikisource text, and attribution for Wikisource, YidTakNL and Pinkas, travel with the files.

## Readiness picture (dry runs, 2026-11-07, tranche v4)

| Run | Real items shipped | Counted / 80 | Printed (counted / 30) | Handwritten (counted / 25) | `source_depth_composition` |
| --- | --- | --- | --- | --- | --- |
| Packaged fixtures (CI) | 21 | 21 | 15 | 4 | blocked: the Wikisource, YidTakNL and Pinkas floors, both modality floors, the total |
| Real tranche v5 (`--real-tranche-root`) | 2,612 | 105 | 68 | 32 | **pass** |

In the tranche run, the payload per source (counted in brackets) and its splits (train / validation / test items, with groups in brackets) are:

| Source | Payload (counted) | Train | Validation | Test |
| --- | --- | --- | --- | --- |
| Wikisource | 1,452 (40) | 1,162 (27) | 145 (17) | 145 (14) |
| YidTakNL | 123 (15) | 111 (1) | 2 (1) | 10 (1) |
| BGU Pinkas | 30 (30) | 30 (1) | 0 | 0 |
| Knesset | 205 (10) | 164 (11) | 21 (4) | 20 (5) |
| Reshumot | 797 (5, toward the total only) | 637 (69) | 80 (8) | 80 (7) |
| NLI | 4 (4) | 4 | 0 | 0 |
| `pinkas_open` | 1 (1) | 1 | 0 | 0 |
| **All, with 2 synthetic** | 2,614 | 2,111 (80.8%) | 248 (9.5%) | 255 (9.8%) |

F8g's tranche split was 65 / 34 / 1.5%. The BGU Pinkas manuscript is one group, so it stays whole in train. The 9 Wikisource crops that F8g lost to the height threshold now ship (below); 3 legacy NLI manuscript seeds still fail it with their 256 px fixture images, as before.

**The other gates in the tranche run** are as in F8g:

| Gate | Status | Why |
| --- | --- | --- |
| `rights_provenance` | pass | |
| `uniqueness_leakage` | pass | 66 work groups, 94 source groups, no leaks; benchmark/holdout `ok`; 3 pinned groups (`benchmark_v1`) |
| `annotation_expectations` | pass | |
| `portability_checksums_archives` | pass | |
| `public_docs` | pass | |
| `synthetic_target_scale` | blocked | 2 / 80 synthetic items; this is unchanged |
| `privacy_review` | blocked | the 4 legacy NLI and BiblIA review-required items; no F8 item is review-required |
| `benchmark_references` | blocked | 1 / 3 reviewed or adjudicated; `benchmark_v1` stays frozen |
| `takedown_removal` | blocked | the private-reporting verification is out of date |

**The text-region crop floor (F8g2).** The 9 crops F8g dropped are 83-199 px tall: one to five transcribed lines cut from a 960 px page render (Artush p. 11, Baer's Seder Avodat Yisrael p. 108, Luzzatto's Bereshit pp. 97, 99, 117, 143, 145 and 493, Buber's Tanhuma p. 266). Each is a legitimate, agent- or tool-checked crop, so the 200 px page threshold was too strict for them. `quality_thresholds.yaml` adds `text_region_crop_minimum_height: 32`, applied only to an item with crop provenance (`metadata.crop`) whose source page itself passes the 200 × 200 page thresholds. 32 px holds one line of small type at the 960 px render (body lines there are 40-50 px apart) and still rejects slivers. Every other asset keeps 200.

**Caveats**

- **Splits follow group integrity first.** Size-aware assignment (§2) brings the tranche to 81 / 9 / 10, but a source of one group (BGU Pinkas) stays whole in train, and YidTakNL's three works give 90 / 2 / 8. Fixture splits moved with the new algorithm; the benchmark items are pinned and did not.
- **Split stability.** A seeded hash order keeps most components in place when the pool changes, but not all: dropping one Wikisource Index moves 13 pages at the median.
- **No scored references yet.** The text is human-made, but it is `not_adjudicated`. It becomes a scored reference only through F2 attestation and adjudication. `benchmark_v1` is unchanged.
