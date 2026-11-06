# Real-source release contract and the promoted real tranche (F8g)

`F8g` moves the F8 real sources from `review_only` into the public dataset path, so real printed and handwritten pages, with their human-made text, actually ship. Plan: [`planning/tasks/f8-real-source-map.md`](../planning/tasks/f8-real-source-map.md). Rights: [`planning/decisions/2026-11-06-f8-real-source-decisions.md`](../planning/decisions/2026-11-06-f8-real-source-decisions.md), decisions 1-13.

It has four parts:

1. a **composition contract**, `real_source_composition.v2`;
2. **leakage governance** at the level of works, editions and scan files, with a hook for works that feed synthetic training;
3. **promotion**, with each source's scope markers and attribution carried into every export;
4. a **real tranche**: the full promoted pool, materialized outside git from pinned caches, with a committed manifest.

`F8g2` hardens it: size-aware group splits (§2), the Pinkas canvas checks, the crop height floor, `wikisource_plain_text.v3`, and a tranche v2 that grows Reshumot and the Knesset protocols past their fixtures (§4).

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
| `reshumot_born_digital` | promoted (F8g) | printed, not counted toward the modality floors | 0 | 5 | PD-IL; `rendered_not_scan`; page text ships |
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
  3. **Pinned** components take their split first and count toward it: a benchmark item's committed `benchmark_split` (read from the benchmark config, so `benchmark_v1` never moves), and a synthetic-training overlap (train).
  4. The other components are visited in seeded order, ascending `sha256(seed + "\0" + component id)` (seed `hocrgen-split-v1`). The order of one component does not depend on the others.
  5. A component of `n` items enters a holdout only if it fits, `count + n ≤ target + 0.5` (the target rounded to the nearest item); among the holdouts it fits, it takes the one with the largest share still open. Otherwise it goes to train.
- Consequences: a group never splits, and a group larger than a holdout's target never goes there, so a one-group stratum (the BGU Pinkas manuscript) stays in train; a stratum too small for half an item in a holdout puts nothing there; with many small groups each holdout is met to within one item. A pool change moves only components visited after it whose fit changes: on the Wikisource pool (58 Indexes, 1,455 pages), dropping one Index moves 13 of the other pages at the median and 3% on average.
- The leakage report's `split_assignment` block gives the algorithm, seed, policy and per-stratum item and group counts. The function is pure (`SplitGroup` in, split per group out), so other tools can place their own groups the same way: the E2d2 real printed reference pool, for example, can call it on its Indexes.
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
- `rendered_not_scan`.

An item that cannot carry its source's terms stops the export. For example, a YidTakNL item without `character_level_only`, or without both of its exclusions, or a Reshumot page without `is_scan: false`.

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

The full pool (tranche v2, `f8g2_real_tranche_v2`) is 1,995 pages and 910 MB. It never enters git. `python -m hocrgen.tools.real_tranche` builds it reproducibly in an operator folder:

```bash
# 1. capture what no operator cache holds yet (network; each file checked against the pin the repo already records)
PYTHONPATH=src python -m hocrgen.tools.real_tranche capture --cache <cache> \
  [--source yidtaknl|pinkas|reshumot|knesset ...] [--pinkas-manifest-copy <F8d2 copy of the NLI manifest>] \
  [--reshumot-per-query 2] [--knesset-per-term 3]
# 2. materialize the tree from the caches (offline; the Wikisource API cache is replayed, and any miss fails; poppler)
PYTHONPATH=src python -m hocrgen.tools.real_tranche materialize --out <tranche>/f8g2_real_tranche_v2 --cache <cache> \
  --wikisource-work-dir <F8b7 inventory work dir> --wikisource-renders <renders dir> [--wikisource-renders ...] \
  --created-at 2026-11-07 --manifest-out src/hocrgen/data/real_tranche
# 3. check every file, and build or export against the tranche (only a tree that matches the committed manifest is accepted)
PYTHONPATH=src python -m hocrgen.tools.real_tranche verify --tranche <tranche>/f8g2_real_tranche_v2
PYTHONPATH=src python -m hocrgen export-public-beta --profile profile_open_v1 --dry-run --real-tranche-root <tranche>/f8g2_real_tranche_v2 ...
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
- **Reshumot:** every page of every captured booklet, through the unchanged F8e gate. A page is kept only when its `pdftotext` text passes the logical-order check and its PDF page holds no image; the render is `pdftoppm` 150 dpi gray (`is_scan: false`).
- **Knesset:** every page of every captured protocol that is one embedded scan, extracted losslessly with `pdfimages`: the 1-bit CCITT scans as PNG, and the colour rescans' JPEG streams byte for byte. Images only.
- The packaged fixture's admitted Reshumot and Knesset pages are kept as packaged.

**The committed manifest** is `src/hocrgen/data/real_tranche/tranche_manifest.json` and `tranche_items.jsonl`. It holds no page text. It records:

- per item: the source, id, source group, modality, asset checksum and size, text checksum, crop flag and upstream provenance;
- per source: the checksums of the snapshot's descriptor files;
- the digest of `SHA256SUMS`.

**Using the tree.** `--real-tranche-root` on the pipeline commands checks the tree against the manifest, then points each tranche source at its snapshot. Every other source keeps its packaged fixture snapshot. Source health writes `tranche://` paths, so no absolute local path reaches an export.

| Source | Pages in the tranche | Groups | Bytes | Left out |
| --- | --- | --- | --- | --- |
| `wikisource_he_proofread` | 1,455 (1,214 full pages, 241 crops) | 58 Indexes | 632 MB | 1 page `text_not_on_page` (Pri Megadim p. 244, F8g2) |
| `yidtaknl_vaybertaytsh_gt` | 123 (121 matched pages, plus the 2 vendored 1781 pages) | 3 works | 164 MB | 33 matched pages whose upstream text file is empty (below) |
| `pinkas_dataset_bgu` | 30 (24 train, 6 test upstream) | 1 manuscript | 49 MB | none |
| `reshumot_born_digital` | 182 (180 captured, 2 fixture) | 26 booklets with a kept page | 19 MB | 706 of 886 captured pages fail the F8e gate (below) |
| `knesset_committee_protocols_pre1976` | 205 (202 captured, 3 fixture) | 20 protocols | 46 MB | none |

NLI keeps its packaged snapshot (10 items); its image server answered HTTP 520 throughout.

**Pass rates of the new captures (F8g2, 2026-11-07)**

- **Reshumot:** 84 booklets, 886 pages (2 more PDFs answered HTTP 500). 180 pages pass (20%): ספר החוקים 153 / 508 (30%), קובץ התקנות 27 / 378 (7%). 594 fail the logical-order check (`extraction_order_not_verified`) and 112 hold an image on the page (`pdf_not_born_digital`). Every passing page is from 2006-2016: **all 314 pages from 2017 on fail**, because their running footer extracts in visual order (reversed words such as `םיקוחה רפס`) and their text carries U+FEFF. That is a converter follow-up for `hocrgen.parsers.pdf_bidi`; the gate is unchanged.
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

## Readiness picture (dry runs, 2026-11-07, tranche v2)

| Run | Real items shipped | Counted / 80 | Printed (counted / 30) | Handwritten (counted / 25) | `source_depth_composition` |
| --- | --- | --- | --- | --- | --- |
| Packaged fixtures (CI) | 21 | 21 | 15 | 4 | blocked: the Wikisource, YidTakNL and Pinkas floors, both modality floors, the total |
| Real tranche v2 (`--real-tranche-root`) | 2,000 | 105 | 68 | 32 | **pass** |

In the tranche run, the payload per source (counted in brackets) and its splits (train / validation / test items, with groups in brackets) are:

| Source | Payload (counted) | Train | Validation | Test |
| --- | --- | --- | --- | --- |
| Wikisource | 1,455 (40) | 1,163 (26) | 146 (24) | 146 (8) |
| YidTakNL | 123 (15) | 111 (1) | 2 (1) | 10 (1) |
| BGU Pinkas | 30 (30) | 30 (1) | 0 | 0 |
| Knesset | 205 (10) | 164 (11) | 21 (4) | 20 (5) |
| Reshumot | 182 (5, toward the total only) | 147 (18) | 17 (3) | 18 (5) |
| NLI | 4 (4) | 4 | 0 | 0 |
| `pinkas_open` | 1 (1) | 1 | 0 | 0 |
| **All, with 2 synthetic** | 2,002 | 1,622 (81.0%) | 186 (9.3%) | 194 (9.7%) |

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
