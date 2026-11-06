# Real-source release contract and the promoted real tranche (F8g)

`F8g` moves the F8 real sources from `review_only` into the public dataset path, so real printed and handwritten pages, with their human-made text, actually ship. Plan: [`planning/tasks/f8-real-source-map.md`](../planning/tasks/f8-real-source-map.md). Rights: [`planning/decisions/2026-11-06-f8-real-source-decisions.md`](../planning/decisions/2026-11-06-f8-real-source-decisions.md), decisions 1-13.

It has four parts:

1. a **composition contract**, `real_source_composition.v2`;
2. **leakage governance** at the level of works, editions and scan files, with a hook for works that feed synthetic training;
3. **promotion**, with each source's scope markers and attribution carried into every export;
4. a **real tranche**: the full promoted pool, materialized outside git from pinned caches, with a committed manifest.

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

- A component's split-group id is the smallest F1d split-group id among its members. An item that shares nothing keeps the split it had before F8g.
- The leakage report adds `work_group_leaks` and `synthetic_training_overlap`. A leak of either kind fails the split stage, as before.

**Benchmark and holdout (F1e)**

- The F1e leakage artifact adds `work_group` risks: a benchmark item sharing a work group with a non-benchmark item.
- It also adds `synthetic_training_work` risks: a benchmark item whose work feeds synthetic training. This kind has no accepted resolution. Such an item must leave the benchmark through a membership change.

**Synthetic-training cross-check**

- `HeOCR/hocrsyngen` plans Project Ben-Yehuda public-domain text as recognizer training text (S15a, `HeOCR/hocrsyngen#90`). Each corpus build will publish a work-level exclusion list. `hletterscriptgen` already crops glyphs from HASH scans (F7).
- The registry `src/hocrgen/config/synthetic_training_works.yaml` (`synthetic_training_works.v1`) records such works, each with the work-group keys of the real items that show it. For example, the `nli_record` keys that `F8f` matched PBY editions to.
- A real item that matches a registered work stays in `train` with its whole component. Its split assignment says `split_constraint: synthetic_training_overlap`.
- The registry is packaged with its two producers and **no works**, because no S15a corpus has been built yet.
- The n-gram overlap check that S15a also asks hocrgen to run (real references against the corpus line index) is left to `HeOCR/hocrgen#102` and E2d.

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

The full pool is about 1,600 pages and 814 MB. It never enters git. `python -m hocrgen.tools.real_tranche` builds it reproducibly in an operator folder:

```bash
# 1. capture what no operator cache holds yet (network; each file checked against the pin the repo already records)
PYTHONPATH=src python -m hocrgen.tools.real_tranche capture --cache <cache> \
  [--pinkas-manifest-copy <F8d2 copy of the NLI manifest>]
# 2. materialize the tree from the caches (offline; the Wikisource API cache is replayed, and any miss fails)
PYTHONPATH=src python -m hocrgen.tools.real_tranche materialize --out <tranche>/f8g_real_tranche_v1 --cache <cache> \
  --wikisource-work-dir <F8b6 inventory work dir> --wikisource-renders <renders dir> [--wikisource-renders ...] \
  --created-at 2026-11-06 --manifest-out src/hocrgen/data/real_tranche
# 3. check every file, and build or export against the tranche (only a tree that matches the committed manifest is accepted)
PYTHONPATH=src python -m hocrgen.tools.real_tranche verify --tranche <tranche>/f8g_real_tranche_v1
PYTHONPATH=src python -m hocrgen export-public-beta --profile profile_open_v1 --dry-run --real-tranche-root <tranche>/f8g_real_tranche_v1 ...
```

**What is captured, and how it is checked**

- **YidTakNL:** the 121 matched pages with text, from the dataset's public SURFdrive share. Each is checked against the share's SHA-1 and byte count in `matched_pages.jsonl`.
- **BGU Pinkas:** the zip from Zenodo, checked against its MD5. The NLI manifest is checked against the pinned capture's upstream sha256.

**What the tree holds**

- `tranche.json` and `SHA256SUMS`.
- `sources/<source_id>/snapshot/` in each fetcher's own packaged snapshot format. The unchanged fetchers and gates read it.
- **Wikisource:** every page the F8b6 inventory passed, rebuilt from its API cache with the committed agent and tool checks. The images are the 960 px Commons renders, unchanged. Each partial page has its crop.
- **YidTakNL and Pinkas:** the upstream images and texts, unchanged.

**The committed manifest** is `src/hocrgen/data/real_tranche/tranche_manifest.json` and `tranche_items.jsonl`. It holds no page text. It records:

- per item: the source, id, source group, modality, asset checksum and size, text checksum, crop flag and upstream provenance;
- per source: the checksums of the snapshot's descriptor files;
- the digest of `SHA256SUMS`.

**Using the tree.** `--real-tranche-root` on the pipeline commands checks the tree against the manifest, then points each tranche source at its snapshot. Every other source keeps its packaged fixture snapshot. Source health writes `tranche://` paths, so no absolute local path reaches an export.

| Source | Pages in the tranche | Bytes | Left out |
| --- | --- | --- | --- |
| `wikisource_he_proofread` | 1,456 (1,215 full pages, 241 crops; 58 Indexes; F8b7) | 631 MB | none |
| `yidtaknl_vaybertaytsh_gt` | 123 (121 matched pages, plus the 2 vendored 1781 pages) | 164 MB | 33 matched pages whose upstream text file is empty |
| `pinkas_dataset_bgu` | 30 (24 train, 6 test upstream) | 49 MB | none |

Reshumot, the Knesset protocols and NLI keep their packaged snapshots: 2, 3 and 10 items. Their upstream pools need new captures; that is a follow-up.

### Hosting proposal (maintainer decision; nothing has been published or uploaded)

The tree is about 814 MB in 4,934 files: JPEG and PNG images, UTF-8 text, PAGE XML and JSON. The licences are mixed, CC BY-SA 4.0, CC BY 4.0 and PD-IL, per item.

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

## Readiness picture (dry runs, 2026-11-06)

| Run | Real items shipped | Counted / 80 | Printed (counted / 30) | Handwritten (counted / 25) | `source_depth_composition` |
| --- | --- | --- | --- | --- | --- |
| Packaged fixtures (CI) | 21 | 21 | 15 | 4 | blocked: the Wikisource, YidTakNL and Pinkas floors, both modality floors, the total |
| Real tranche (`--real-tranche-root`) | 1,611 | 95 | 61 | 32 | **pass** |

In the tranche run, the per-source payload counts (counted in brackets) are:

- Wikisource 1,448 (40);
- YidTakNL 123 (15);
- Pinkas 30 (30);
- NLI 4 (4: 3 printed books and 1 manuscript);
- Knesset 3 (3);
- Reshumot 2 (2, toward the total only);
- `pinkas_open` 1 (1).

9 Wikisource crops are dropped by the unchanged normalize height threshold.

**The other gates in the tranche run:**

| Gate | Status | Why |
| --- | --- | --- |
| `rights_provenance` | pass | |
| `uniqueness_leakage` | pass | 66 work groups, 52 source groups, no leaks |
| `annotation_expectations` | pass | |
| `portability_checksums_archives` | pass | |
| `public_docs` | pass | |
| `synthetic_target_scale` | blocked | 2 / 80 synthetic items; this is unchanged |
| `privacy_review` | blocked | the 4 legacy NLI and BiblIA review-required items; no F8 item is review-required |
| `benchmark_references` | blocked | 1 / 3 reviewed or adjudicated; `benchmark_v1` stays frozen |
| `takedown_removal` | blocked | the private-reporting verification is out of date |

So composition, the blocker this PR owns, closes on the tranche. Publication stays blocked by the other four gates.

**Caveats**

- **Lumpy splits.** Whole groups are assigned to splits, and there are few groups (58 Wikisource Indexes, 2 YidTakNL works, 1 Pinkas manuscript). The tranche split is 65 / 34 / 1.5% train / validation / test, against the 80 / 10 / 10 policy. All Pinkas and YidTakNL pages land in train. A size-aware group assignment is a follow-up; it would move existing fixture splits.
- **No scored references yet.** The text is human-made, but it is `not_adjudicated`. It becomes a scored reference only through F2 attestation and adjudication. `benchmark_v1` is unchanged.
