# Decision 2026-11-18: an IA item whose description names its digitizer is a known source

- **Date:** 2026-11-18
- **Decided by:** the maintainer, Shay Palachy Affek. heocr-lead asked him, in the lead session, whether Internet Archive scans should count as a known source when their description names who digitized them; today the gate rejects them as anonymous uploads. His answer: "Yes, allow it" (Shay Palachy Affek, 2026-11-18). The per-item terms below are heocr-lead's, relayed with the answer.
- **Status:** accepted
- **Amends:** condition 3 of `2026-11-09-internet-archive-library-scans.md` ("The source is known. Anonymous uploads with no known scanning library are excluded."). The maintainer set that condition himself, so the change is his.
- **Builds on:** `2026-11-10-legal-strategy.md` (Routes B and C, per-item rights justification, and the ruling on NLI-origin files: "Yes, same logic"); `2026-11-11-text-sources-sefaria-gutenberg.md` (item 6: an uploader e-mail address is never evidence).
- **Code:** `hocrgen.fetchers.ia_iiif.decide_ia_rights` (`known_source_from_description`), the aligner's `--text-source sefaria` path, and `hocrgen.fetchers.ia_justification` (`digitizer.source_established`). Tests: `tests/test_ia_known_source.py`.
- **Context:** `docs/phist_round_inputs_plan.md`, Tier B. Most of the rabbinic supply for the P-hist round is on IA as uploads with no `contributor` library, whose description says who scanned them.

## Rule

An IA item with no library in `contributor`, and not Google-digitized, is a **known source** when its description (or its `source`, `notes` or `provenance` field) has a digitizer statement, such as "Scanned by X" or "digitized by the X". The statement must pass the check for its kind:

| Digitizer named | Also required |
|---|---|
| The National Library of Israel | The item cites an NLI record (a `99…5171` id, or an `NNL_ALEPH` number). |
| Sefaria | The Sefaria version of the text aligned to it is `digitizedBySefaria`, and its `versionSource` cites an NLI record that the IA item also cites. |
| Any other named digitizer (for example a university library) | Nothing more: the name is the evidence. |

- A statement whose "name" is an e-mail address, or a redacted one, is no evidence (decision 2026-11-11, item 6). Uploader fields are never read.
- "Uploaded by …" is not a digitizer statement.
- A description that names no digitizer is still rejected as `ia_anonymous_upload_no_known_library`. When a statement fails its check, its reason is recorded too: `ia_nli_scan_cites_no_nli_record`, `ia_sefaria_scan_needs_sefaria_version`, `ia_sefaria_version_not_digitized_by_sefaria`, `ia_sefaria_scan_cites_no_nli_record` or `ia_sefaria_scan_nli_record_mismatch`.
- **The rest of the IA gate is unchanged:**
  - condition 1: a public-domain printed text;
  - the Google class and its hygiene;
  - condition 5: no restrictive `licenseurl` or `rights`;
  - every accepted item needs its own `rights_justification`.

## How the source was established (per item)

Every decision records `known_source`, and an accepted item's `digitizer.source_established` carries the same record into its rights justification. It holds:
- `basis: description_names_digitizer`, and this record's path;
- every statement found, each with its field, a quote of the description around it, the name, its kind, and the check and its result;
- the NLI record ids the item cites;
- for Sefaria, the version's title, `versionTitle`, `versionSource`, `digitizedBySefaria`, and the NLI record ids it cites.

## What this opens (checked on 2026-11-18 snapshots)

- **Accepted now:**
  - NLI's own scans mirrored on IA that name NLI and cite the record, such as `radaq-bereshit-pressburg-1842-images` and `haameq-davar-vilna-1879-images`;
  - the Vilna Shas mirror `Talmud_Bavli_Vilna_images`, whose description says "Scanned by Duke University Libraries".
- **Accepted with the Sefaria version:** the Tur mirror `arbaah_turim_vilna_images`. Its description says the set was scanned by Sefaria and cites the NLI record of Sefaria's Tur version.
- **Still rejected:** Sefaria's own uploads `radbaz`, `ari_sefaria_201601` and `NodaBYehuda`, and `KafHaChayimVol.I`. Their descriptions name no digitizer; only the uploader field points to Sefaria, and it is never read. They need another source of evidence, or the Commons copies of the same scans (Route C), whose file pages say "Scan by Sefaria of NNL_ALEPH…".
- **Items that mix several digitizers** record every statement. Their pages from other sources (for example HebrewBooks fill-in pages, or another printing) are a matter for edition matching and alignment, not for this gate.

— data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource
