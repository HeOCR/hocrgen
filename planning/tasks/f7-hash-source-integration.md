# F7 — Governed HASH real-handwriting source integration

Status: `F7a` planning and the `F7b` review-only adapter are implemented on the current ref; `F7c` is **deferred** (no valid inputs); `F7d`–`F7e` are planned. Parent milestone: F7. It feeds the `F6g` readiness rerun. Source proposal: `HeOCR/hocrgen#89`.

The evidence was checked against `HeOCR/hash` commit `3cb163a`: 197 entries in 48 source groups. The scans come from NLI (143), the Library of Congress (24), Wikimedia Commons (29) and OPenn (1). Most date from 1900–1949 (158); 31 are pre-1900 and 5 are from 1950 on.

## Rights mapping

| HASH `license_expression` | n | hocrgen mapping | Source id |
| --- | --- | --- | --- |
| `LicenseRef-Public-Domain-Israel` (NLI "Any Use Permitted") | 143 | `PD-IL`, exact match on the NLI statement | `hash_nli_any_use` |
| `PDM-1.0` (LoC, Commons) | 44 | new `PDM-1.0` (`open`) | `hash_public_domain` |
| `LicenseRef-Public-Domain-Ukraine` | 1 | `PDM-1.0` | `hash_public_domain` |
| `CC-BY-SA-3.0` (Commons uploader licence) | 9 | rejected at the adapter; never a candidate | none |

The CC-BY-SA-3.0 lane is rejected rather than routed to review for three reasons. The uploader licence does not establish rights in letters whose authors died between 1966 and 2015. The lane includes copyrighted Yiddish. HASH's own ingest policy excludes 3.0-era licences. The adapter must reject these entries outright, because `privacy_review` requires `blocked_count == 0` in the governed pool.

The v1 scope filter also excludes the Aramaic entry (1) and the Hebrew/Hungarian `hebrew_extent: partial` pages (11). That leaves an eligible pool of 176 entries in 39 source groups.

Both source ids are `status: review_only`, with `default_public_release: false` and `requires_manual_review: false`. Their privacy source default is `clear` (see Privacy). Neither appears in `profile_open_v1` until `F7d`. That hold is not about privacy. `F7d` must first change the per-source real target contract, govern writer-group overlap with synthetic training data (see Leakage), and vendor the promoted tranche's assets; the packaged snapshot holds only fixture thumbnails.

## Privacy

**Maintainer decision, 2026-11-06: HASH needs no human privacy review.** In the maintainer's words: "no need for human to go over privacy; if that is a guideline or rule written somewhere, it is in error and you must remove it; these are all public domain, and everything there is about people who've been dead for decades."

This removes the earlier rules: the per-page privacy review, the per-writer cap on a public tranche, the separate review of the Hannah Senesh diaries for passages written as a minor, and "review, then approve" for the Commons letters. Both HASH privacy source defaults are `clear`, and `requires_manual_review` is `false`. HASH adds no `privacy_review` decisions. The general `identity_document_block` pattern rule still applies to every source; it blocks automatically and asks for no human review.

## Fixtures and adapter type

The adapter uses packaged static records, following the Pinkas/BiblIA pattern. `src/hocrgen/data/hash/records.json` is a hocrgen-owned projection of a pinned HASH commit. Each record carries the upstream `entry_id`, a checksum, `source_group` (the HASH `source_id`), `writer_group` (the creator) and the rights evidence. CI uses small committed fixtures plus rejection and scope-filter fixtures, with no network access. Promoted-tranche assets are vendored in `F7d` (about 14 MiB for 20 pages). The full inventory stays operator-only.

## Ground-truth boundary (F7c)

**Deferred on 2026-11-01.** `F7c` has no valid inputs:

- The issue #86 maintainer decisions (2026-11-01) rule out any new human transcription campaign or labeling target. Issue #86 (tender pages) has since been closed on 2026-11-06 as unusable; whether this no-campaign rule still stands is an open question for the maintainer.
- None of the 10 HASH `status: reviewed` transcripts meets the human-reviewed bar (see below).

Until human-attested inputs exist without a new campaign, HASH text may be scored only as explicitly `unreviewed` diagnostics through E2c evaluation, never as references. Source proposal #89 stays open. The design below is kept for when inputs exist.

HTR candidate output is never ground truth. This covers the Kraken/eScriptorium, consolidated and GPT-4o files under HASH `data/transcripts/candidates/`, and any `created_by: ocr` text without a human attestation. None of the current 10 `status: reviewed` HASH texts qualifies:

- 4 began as GPT-4o output; its evidence text still says it needs human review.
- 6 began as Wikisource edition texts.
- All 10 were then edited toward the page image in HASH `cf1d4d4` by an agent, with no human reviewer recorded. They now follow the visible main text, but they remain unreviewed. The 6 edition-based texts keep full niqqud that the autographs mostly lack, and page numbers, stamps and marginal notes are left out.

The converter accepts a text only when a HASH attestation record matches it. The record must name a human reviewer, the method, the base text, the niqqud policy (as visible) and the text SHA-256. For each accepted text, the converter:

- emits NFC, logical-order line references;
- maps uncertainty markers to `uncertain` spans;
- sets `adjudication_status: adjudicated` only from an explicit adjudication record.

Output goes to an operator-only `hash_reference_pool_v1` manifest. It never edits `benchmark_v1`.

## Gate impact

| Gate | Current ref | HASH contribution |
| --- | --- | --- |
| `source_depth_composition` | 2 / 80 (NLI 1/27, Pinkas 1/27, BiblIA 0/26) | 0 until `F7d` changes the per-source contract. With floors of 10 per source and 80 in total, HASH can supply up to 50. |
| `benchmark_references` | 1 / 3 | 0 for frozen `benchmark_v1`; `F7e` proposes `benchmark_v2`. |

## Leakage

`hletterscriptgen` crops glyphs from HASH scans, and those glyphs feed `hocrsyngen` through `hletterscript`. HASH items therefore carry `writer_group`, so that `F7d` can govern writer-level overlap between real test or benchmark items and synthetic training data.
