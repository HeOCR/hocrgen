# E2f — Evaluation-reserved units: the training-input guard (decisions 0017, 0018)

Status: **`E2f1` merged (#178); `E2f2` in review (#187); `E2f3` merged (#188); `E2f4` planned.** Parent milestone: E2, Baselines and evaluation utilities. heocr-eval owns the printed-modern evaluation units and lists them in `pmod_unit_split_v<N>.json`. hocrgen records that file in `eval_reserved_units.v1` and refuses eval and unassigned units as training input. Contract: [`docs/real_source_release_contract.md`](../../docs/real_source_release_contract.md) §2, *Evaluation-reserved units*.

## Notation

| Notation | Scope | State |
| --- | --- | --- |
| `E2f1` | `eval_reserved_units.v1`, generated from `pmod_unit_split_v1.json` by `hocrgen.tools.eval_reserved_units sync`; unit ids for `reshumot_born_digital` and `knesset_committee_protocols_pre1976`; the `eval_reserved` release split; the fail-closed guard in every training-input builder. Recorded retroactively. | merged (#178) |
| `E2f2` | Two more governed sources. `reshumot_scanned` (`reshumot_scanned:<series>_<n>`, its own prefix) and `knesset_plenary_k1_12` (`plenary:K<knesset>_<sitting>`), with unit, group and page id patterns. The registry refuses a booklet listed in both Reshumot sources. Their rows are unassigned until a split version lists them. | in review (#187) |
| `E2f3` | Sync to `pmod_unit_split_v2` (issued, sha256 `a75ed685…`). It adds only the 121 born-digital 2005 booklets, all `non_eval`. | merged (#188) |
| `E2f4` | Sync to `pmod_unit_split_v3`. It will add the `reshumot_scanned` and `knesset_plenary_k1_12` units once their enumeration and the mid-century split exist. Until then their rows stay unassigned and refused. | planned |
