# Knesset plenary: public-person roster

`public_roster_v1.json` lists the people the plenary private-name gate
(`hocrgen.privacy.plenary_names`, decision `planning/decisions/2026-11-13-plenary-private-names.md`) treats as public.

- **Source:** the Knesset's public OData v4 feed, `https://knesset.gov.il/OdataV4/ParliamentInfo/`, fetched on 2026-11-13. The fetch used `$top`/`$skip` paging, no `$expand`, and one request every 3 seconds.
- **Rows:** every `KNS_Person` (1,235) that has at least one `KNS_PersonToPosition` row (24,021 rows). That leaves 1,211 people: MKs, ministers and deputy ministers since 1949.
- **Fields kept per person:** `person_id`, `first`, `last`, and `knessets`, the distinct `KNS_PersonToPosition.KnessetNum` values. No other `KNS_Person` field is copied; e-mail addresses in particular are not.
- **`factions_by_knesset`:** the distinct `KNS_PersonToPosition.FactionName` values for each term. The gate uses them to prove speaker headings.
- **Refresh:** re-fetch, rebuild, and bump the file version. The gate records the roster's sha256 in every build summary.
