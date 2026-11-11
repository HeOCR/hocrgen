"""Decisions 0017 and 0018: per-node evaluation slices, cluster intervals, page, order and line measures.

The report blocks built here are added to ``evaluate-references`` output only when their flags are used
(``--eval-labels``, single-engine ``--bootstrap-resamples`` with ``--bootstrap-clusters``, ``--line-references``); a run
without them is byte-identical to one before this module existed.

- **Labels** (``hocrgen_eval_labels.v1``) place every scored item on a node of the decision-0018 document tree
  (``printed/new_printed``, ``printed/old_printed``, ``modern_mixed/forms``, ``handwritten/new``, ``handwritten/old`` or
  ``unclassified``), with optional ``facets`` (``genre``, ``font``) and a ``niqqud`` stratum (``pointed``, ``light``,
  ``unpointed``). A scored item without a label fails the run: it is never counted as "unknown".
- **Slices** are ``slices[node][facet | "ALL"][niqqud key]``; facet keys are ``genre=<v>`` and ``font=<v>`` for the
  values present. The niqqud keys are ``excluding_pointed`` (the node's headline at ``[node]["ALL"]``, on primary.v1),
  ``ALL`` (with pointed items; every node except the vertical, ``printed/new_printed``, whose numbers never include
  pointed text) and each niqqud value present. The ``pointed`` slice is scored on ``consonantal.v1`` only.
  ``unclassified`` is flagged ``not_a_set`` and has no headline.
- **No blended numbers** (decision 0018 §5): there is no cross-node aggregate. With labels, ``strata`` keeps only the
  ``node`` dimension (one record per node); facet and niqqud breakdowns live only inside each node's slices. An aggregate, when one is added, must
  state the weight of every subset it averages.
- **Intervals** are 95% percentile cluster bootstraps of each engine's own CER and WER (the existing
  ``paired_bootstrap_interval`` with a ``(0, units)`` baseline), and paired intervals of every comparison delta. A slice
  with fewer than 3 clusters gets no interval (``too_few_clusters``); fewer than 8 is flagged ``low_cluster_count``.
- **Page-CER distribution:** median, p90 (nearest rank) and the share of items with CER < 0.02, < 0.05 and < 0.10.
- **Order diagnostic:** ``order_cost`` = page-order primary CER minus ``line_matched.v1`` primary CER over the same
  items with at least two reference lines, and, only where reference lines are physical lines
  (``reading_order_verified: within_line``), ``missed_line_rate``. Diagnostic only; never a recognition score.
- **Line references** (``line_verify_line_references.v1``, a line_verify ``line_set``): each verified line crop is an
  item, labelled like a page by its line item id. Exact-line rate, line CER and the line-CER distribution (median,
  p90, share <= 0.02 and <= 0.05). A line whose ``reference_views`` are consonantal only (``pointed_print``) is scored
  on ``consonantal.v1`` only. Clusters are the line's source unit (``book_id``).
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_evaluation import (
    NORMALIZATION_PROFILES,
    PRIMARY_PROFILE_ID,
    _aggregate,
    _pair,
    line_matched_prediction,
)

EVAL_LABELS_SCHEMA = "hocrgen_eval_labels.v1"
VERTICAL = "printed/new_printed"  # decision 0018 §4: the vertical; its numbers never include pointed text
UNCLASSIFIED = "unclassified"
NODES = (VERTICAL, "printed/old_printed", "modern_mixed/forms", "handwritten/new", "handwritten/old", UNCLASSIFIED)
NIQQUD_VALUES = ("pointed", "light", "unpointed")
FONT_VALUES = ("modern_serif", "modern_sans", "typewriter")
FACETS = ("genre", "font")
LABEL_KEYS = ("node", "niqqud")
# E2e.1: ``exposed`` lists the model ids that saw the item (training, or selection dev); with ``exposure_reason``.
OPTIONAL_LABEL_KEYS = ("facets", "exposed", "exposure_reason")
LABEL_DIMENSIONS = ("node", *FACETS, "niqqud")  # strata added to items; an unset facet is "unset"
# With labels, the only report-level stratum is the node: any other dimension would pool items of several nodes
# (decision 0018 §5). Facet and niqqud breakdowns live inside each node's slices.
NODE_DIMENSIONS = ("node",)
UNSET = "unset"
CONSONANTAL_PROFILE_ID = "consonantal.v1"
POINTED = "pointed"
ALL = "ALL"
EXCLUDING_POINTED = "excluding_pointed"
TOO_FEW_CLUSTERS = 3
LOW_CLUSTER_COUNT = 8
PAGE_THRESHOLDS = (0.02, 0.05, 0.10)  # share of pages with CER strictly below
LINE_THRESHOLDS = (0.02, 0.05)  # share of lines with CER at or below
LINE_REFERENCES_SCHEMA = "line_verify_line_references.v1"  # hocrgen.tools.line_verify.LINE_SET_SCHEMA
LINE_REFERENCE_VIEWS = frozenset({"primary", "consonantal"})
LINE_CLUSTER_KEY = "book_id"
SLICES_KIND = "eval_slices.v1"
CONFIDENCE = 0.95
HEADLINE_RULE = ("one headline per node of the decision-0018 tree: slices[node]['ALL']['excluding_pointed'] on primary.v1; "
                 "no blended cross-node number; pointed items are scored on consonantal.v1 only in their own pointed "
                 f"slice, and also inside 'ALL' for every node but the vertical ({VERTICAL}); {UNCLASSIFIED} is "
                 "not_a_set and has no headline")


# --- labels -----------------------------------------------------------------------------------------------------

def load_eval_labels(path: Path) -> dict[str, Any]:
    """Read and validate a ``hocrgen_eval_labels.v1`` file; any malformed label fails closed."""
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageExecutionError(f"could not read eval labels {path.name}: {exc}") from exc
    where = f"eval labels {path.name}"
    if not isinstance(payload, dict) or payload.get("schema_version") != EVAL_LABELS_SCHEMA:
        raise StageExecutionError(f"{where} must use schema_version {EVAL_LABELS_SCHEMA}")
    rule, provenance, labels = payload.get("rule"), payload.get("provenance"), payload.get("labels")
    if not isinstance(rule, str) or not rule.strip():
        raise StageExecutionError(f"{where} needs the rule text")
    if not provenance or not isinstance(provenance, (str, dict)):
        raise StageExecutionError(f"{where} needs a provenance string or object")
    if not isinstance(labels, dict) or not labels:
        raise StageExecutionError(f"{where} needs a non-empty labels object of item id -> label")
    exposure: dict[str, dict[str, Any]] = {}
    for item_id, label in labels.items():
        if not isinstance(item_id, str) or not item_id or not isinstance(label, dict):
            raise StageExecutionError(f"{where}: each label must be an object keyed by a non-empty item id")
        if not set(LABEL_KEYS) <= set(label) or not set(label) <= {*LABEL_KEYS, *OPTIONAL_LABEL_KEYS}:
            raise StageExecutionError(f"{where}: label for {item_id} must have node and niqqud, and optionally "
                                      f"{', '.join(OPTIONAL_LABEL_KEYS)}")
        if label["node"] not in NODES:
            raise StageExecutionError(f"{where}: {item_id} node must be one of {list(NODES)}")
        if label["niqqud"] not in NIQQUD_VALUES:
            raise StageExecutionError(f"{where}: {item_id} niqqud must be one of {list(NIQQUD_VALUES)}")
        facets = label.get("facets") or {}
        if not isinstance(facets, dict) or not set(facets) <= set(FACETS):
            raise StageExecutionError(f"{where}: {item_id} facets must be an object with keys from {list(FACETS)}")
        genre, font = facets.get("genre"), facets.get("font")
        if genre is not None and (not isinstance(genre, str) or not genre.strip() or genre == UNSET):
            raise StageExecutionError(f"{where}: {item_id} facets.genre must be a non-empty string or null")
        if font is not None and font not in FONT_VALUES:
            raise StageExecutionError(f"{where}: {item_id} facets.font must be one of {list(FONT_VALUES)} or null")
        exposed, reason = label.get("exposed"), label.get("exposure_reason")
        if exposed is None and reason is None:
            continue
        if (not isinstance(exposed, list) or not exposed or len(set(exposed)) != len(exposed)
                or not all(isinstance(model, str) and model.strip() for model in exposed)):
            raise StageExecutionError(f"{where}: {item_id} exposed must be a non-empty list of distinct model ids")
        if not isinstance(reason, str) or not reason.strip():
            raise StageExecutionError(f"{where}: {item_id} exposed needs a non-empty exposure_reason")
        exposure[item_id] = {"models": list(exposed), "reason": reason}
    result = {"labels": {k: label_strata(v) for k, v in labels.items()}, "rule": rule, "provenance": provenance,
              "sha256": hashlib.sha256(raw).hexdigest()}
    if exposure:
        result["exposure"] = exposure
    return result


def label_strata(label: Mapping[str, Any]) -> dict[str, str]:
    """A validated label as flat strata: node, genre, font, niqqud (an unset facet is ``"unset"``)."""
    facets = label.get("facets") or {}
    return {"node": label["node"], **{facet: facets.get(facet) or UNSET for facet in FACETS}, "niqqud": label["niqqud"]}


def require_labels(item_ids: Iterable[str], labels: Mapping[str, Any], where: str) -> None:
    missing = sorted(set(item_ids) - labels.keys())
    if missing:
        raise StageExecutionError(f"--eval-labels has no label for {len(missing)} scored {where} item(s), for example "
                                  f"{missing[0]}; unlabelled items are never counted as unknown")


def apply_label_strata(report: dict[str, Any], labels: Mapping[str, Mapping[str, str]],
                       excluded: Iterable[str] = ()) -> None:
    """Add the label dimensions to each item's strata, and the ``node`` aggregate to the report's strata.

    Facet and niqqud breakdowns pool items across nodes, so they appear only inside each node's ``eval_slices``.
    Items in ``excluded`` (exposed to the scored model, E2e.1) are left out of the node aggregate.
    """
    for item in report["items"]:
        item["strata"].update(labels[item["item_id"]])
    profile_ids = list(report["profiles"])
    skipped = set(excluded)
    kept = [item for item in report["items"] if item["item_id"] not in skipped]
    for dimension in NODE_DIMENSIONS:
        values = sorted({item["strata"][dimension] for item in kept})
        report["strata"][dimension] = {
            value: {pid: _aggregate([item["profiles"][pid] for item in kept
                                     if item["strata"][dimension] == value]) for pid in profile_ids}
            for value in values
        }


def exposure_exclusions(item_ids: Iterable[str], labels: Mapping[str, Any] | None,
                        model_ids: Mapping[str, str | None]) -> dict[str, Any] | None:
    """E2e.1: items whose label lists a scored model in ``exposed``; None when the labels carry no exposure.

    ``model_ids`` maps each scored side (``scored``, or ``baseline`` and ``candidate``) to its model id. An item is
    excluded when any side's model saw it, so a paired comparison drops it when either side is exposed.
    """
    exposure = (labels or {}).get("exposure")
    if not exposure:
        return None
    missing = sorted(side for side, model in model_ids.items() if model is None)
    if missing:
        raise StageExecutionError(f"--eval-labels marks items exposed but no model id was given for the {missing[0]} "
                                  "predictions (--model-id / --baseline-model-id); exposure cannot be checked")
    excluded: dict[str, dict[str, Any]] = {}
    for item_id in sorted(set(item_ids)):
        info = exposure.get(item_id)
        sides = sorted(side for side, model in model_ids.items() if info and model in info["models"])
        if sides:
            excluded[item_id] = {"reason": info["reason"], "sides": sides}
    return {"model_ids": dict(model_ids),
            "rule": "an item whose label lists a scored model id in exposed is left out of every eval_slices number",
            "count": len(excluded), "item_ids": list(excluded),
            "reasons": {item_id: entry["reason"] for item_id, entry in excluded.items()},
            "exposed_sides": {item_id: entry["sides"] for item_id, entry in excluded.items()}}


# --- grouping ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class _Group:
    ids: tuple[str, ...]
    profiles: tuple[str, ...] | None = None  # None: every evaluated profile
    headline: bool = False
    not_a_set: bool = False


def _group_tree(items: list[dict[str, Any]], *, dimensions: Iterable[str], labelled: bool) -> dict[str, Any]:
    tree: dict[str, Any] = {"strata": {}}
    for dimension in dimensions:
        values = sorted({item["strata"][dimension] for item in items})
        tree["strata"][dimension] = {value: _Group(tuple(i["item_id"] for i in items if i["strata"][dimension] == value))
                                     for value in values}
    if labelled:
        tree["slices"] = _node_tree(items)
    return tree


def _node_tree(items: list[dict[str, Any]]) -> dict[str, Any]:
    def ids(selected: list[dict[str, Any]]) -> tuple[str, ...]:
        return tuple(item["item_id"] for item in selected)

    tree: dict[str, Any] = {}
    for node_id in NODES:
        in_node = [item for item in items if item["strata"]["node"] == node_id]
        if not in_node:
            continue
        unclassified = node_id == UNCLASSIFIED
        subsets = {ALL: in_node}
        for facet in FACETS:
            for value in sorted({item["strata"][facet] for item in in_node} - {UNSET}):
                subsets[f"{facet}={value}"] = [item for item in in_node if item["strata"][facet] == value]
        tree[node_id] = {}
        for key, members in subsets.items():
            node = {EXCLUDING_POINTED: _Group(ids([i for i in members if i["strata"]["niqqud"] != POINTED]),
                                              headline=key == ALL and not unclassified, not_a_set=unclassified)}
            if node_id != VERTICAL:
                node[ALL] = _Group(ids(members), not_a_set=unclassified)
            for value in NIQQUD_VALUES:
                selected = [item for item in members if item["strata"]["niqqud"] == value]
                if selected:
                    node[value] = _Group(ids(selected), profiles=(CONSONANTAL_PROFILE_ID,) if value == POINTED else None,
                                         not_a_set=unclassified)
            tree[node_id][key] = node
    return tree


def _map_tree(node: Any, render: Callable[[_Group], dict[str, Any]]) -> Any:
    if isinstance(node, _Group):
        return render(node)
    return {key: _map_tree(value, render) for key, value in node.items()}


# --- statistics -------------------------------------------------------------------------------------------------

def cluster_flags(count: int) -> list[str]:
    if count < TOO_FEW_CLUSTERS:
        return ["too_few_clusters"]
    return ["low_cluster_count"] if count < LOW_CLUSTER_COUNT else []


def cer_distribution(values: Iterable[float | None], *, line: bool = False) -> dict[str, Any]:
    """Median, nearest-rank p90 and threshold shares of per-unit CER (units with no reference characters left out)."""
    rates = sorted(value for value in values if value is not None)
    thresholds = LINE_THRESHOLDS if line else PAGE_THRESHOLDS
    comparison = "le" if line else "lt"
    result: dict[str, Any] = {"units": len(rates), "median": None, "p90": None}
    result.update({f"share_cer_{comparison}_{threshold:.2f}": None for threshold in thresholds})
    if not rates:
        return result
    result["median"] = statistics.median(rates)
    result["p90"] = rates[max(0, math.ceil(0.9 * len(rates)) - 1)]
    for threshold in thresholds:
        hits = sum((rate <= threshold) if line else (rate < threshold) for rate in rates)
        result[f"share_cer_{comparison}_{threshold:.2f}"] = hits / len(rates)
    return result


def _bootstrap(baseline: list[tuple[int, int]], candidate: list[tuple[int, int]], clusters: list[str],
               settings: Mapping[str, int]) -> list[float] | None:
    from hocrgen.reference_runs import paired_bootstrap_interval  # reference_runs imports this module

    return paired_bootstrap_interval(baseline, candidate, resamples=settings["resamples"], seed=settings["seed"],
                                     clusters=clusters)


def _units(parts: list[Mapping[str, Any]], edits: str, units: str) -> list[tuple[int, int]]:
    return [(part[edits], part[units]) for part in parts]


def _single_intervals(parts: list[Mapping[str, Any]], clusters: list[str], settings: Mapping[str, int]) -> dict[str, Any]:
    count = len(set(clusters))
    out: dict[str, Any] = {"interval_clusters": count, "interval_flags": cluster_flags(count),
                           "cer_ci": None, "wer_ci": None}
    if count < TOO_FEW_CLUSTERS:
        return out
    for metric, edits, units in (("cer", "character_edits", "reference_characters"), ("wer", "word_edits", "reference_words")):
        candidate = _units(parts, edits, units)
        out[f"{metric}_ci"] = _bootstrap([(0, u) for _, u in candidate], candidate, clusters, settings)
    return out


def _slice_header(group: _Group, profile_ids: list[str], clusters: Mapping[str, str] | None) -> tuple[dict, list[str]]:
    record: dict[str, Any] = {"items": len(group.ids)}
    if group.headline:
        record["headline"] = True
    flags: list[str] = ["not_a_set"] if group.not_a_set else []
    selected = [pid for pid in profile_ids if group.profiles is None or pid in group.profiles]
    if group.profiles is not None:
        record["profile_scope"] = "consonantal_only"
        if not selected:
            flags.append("consonantal_profile_not_evaluated")
    if clusters is not None:
        record["clusters"] = len({clusters[item_id] for item_id in group.ids})
        flags.extend(cluster_flags(record["clusters"]) if group.ids else [])
    record["flags"] = flags
    return record, selected


def _order_record(item_ids: Iterable[str], order: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    rows = [order[item_id] for item_id in item_ids if item_id in order and order[item_id]["reference_lines"] >= 2]
    if not rows:
        return None
    page = _aggregate([row["page_order"] for row in rows])
    matched = _aggregate([row["line_matched"] for row in rows])
    record: dict[str, Any] = {
        "diagnostic_only": True, "profile": PRIMARY_PROFILE_ID, "items": len(rows),
        "page_order_cer": page["cer"], "line_matched_cer": matched["cer"],
        "order_cost": None if None in (page["cer"], matched["cer"]) else page["cer"] - matched["cer"],
    }
    physical = [row for row in rows if row["physical_lines"]]
    if physical:
        reference_lines = sum(row["reference_lines"] for row in physical)
        record["missed_line_items"] = len(physical)
        record["missed_line_rate"] = (1 - sum(row["matched_lines"] for row in physical) / reference_lines
                                      if reference_lines else None)
    return record


# --- single-engine and paired slice blocks ----------------------------------------------------------------------

def _settings_block(*, labels: Mapping[str, Any] | None, clusters: Mapping[str, Any] | None,
                    bootstrap: Mapping[str, int] | None, profile_ids: list[str], mode: str) -> dict[str, Any]:
    block: dict[str, Any] = {"kind": SLICES_KIND, "decisions": ["heocr-engine planning/decisions/0017", "heocr-engine planning/decisions/0018"], "unit": mode,
                             "profiles": profile_ids, "aggregation": "micro: summed edits over summed reference units"}
    if labels is not None:
        block["headline_rule"] = HEADLINE_RULE
        block["labels"] = {"schema_version": EVAL_LABELS_SCHEMA, "sha256": labels["sha256"], "rule": labels["rule"],
                           "provenance": labels["provenance"]}
    if clusters is not None and bootstrap is not None:
        block["cluster_bootstrap"] = {"resamples": bootstrap["resamples"], "seed": bootstrap["seed"],
                                      "confidence": CONFIDENCE, "cluster_key": clusters["cluster_key"],
                                      "method": "percentile interval over whole clusters resampled with replacement",
                                      "too_few_clusters_below": TOO_FEW_CLUSTERS,
                                      "low_cluster_count_below": LOW_CLUSTER_COUNT}
    return block


def slice_report(items: list[dict[str, Any]], *, profile_ids: list[str], labels: Mapping[str, Any] | None,
                 clusters: Mapping[str, Any] | None, bootstrap: Mapping[str, int] | None,
                 order: Mapping[str, Mapping[str, Any]] | None = None, mode: str = "page",
                 exclusions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Per-stratum and per-slice single-engine measures over profile-report ``items``.

    ``items`` are ``{item_id, strata, profiles: {profile_id: pair}}``; an item may lack a profile (a line reference
    for consonantal views only), and each profile is aggregated over the items that have it. Items listed in
    ``exclusions`` (``exposure_exclusions``) enter no number and are reported under ``excluded_exposed``.
    """
    items = _without_exposed(items, exclusions)
    cluster_map = clusters["clusters"] if clusters is not None else None
    if cluster_map is not None:
        missing = sorted(item["item_id"] for item in items if item["item_id"] not in cluster_map)
        if missing:
            raise StageExecutionError(f"--bootstrap-clusters has no cluster for {len(missing)} scored item(s), for "
                                      f"example {missing[0]}")
    by_id = {item["item_id"]: item for item in items}
    dimensions = NODE_DIMENSIONS if labels is not None else sorted({key for item in items for key in item["strata"]})

    def render(group: _Group) -> dict[str, Any]:
        record, selected = _slice_header(group, profile_ids, cluster_map)
        record["profiles"] = {}
        for pid in selected:
            members = [by_id[item_id] for item_id in group.ids if pid in by_id[item_id]["profiles"]]
            parts = [member["profiles"][pid] for member in members]
            entry = _aggregate(parts)
            if mode == "line":
                entry["line_cer"] = entry["cer"]
                entry["exact_line_rate"] = sum(part["exact_match"] for part in parts) / len(parts) if parts else None
                entry["line_cer_distribution"] = cer_distribution((part["cer"] for part in parts), line=True)
            else:
                entry["page_cer_distribution"] = cer_distribution(part["cer"] for part in parts)
            if cluster_map is not None and bootstrap is not None:
                entry.update(_single_intervals(parts, [cluster_map[m["item_id"]] for m in members], bootstrap))
            record["profiles"][pid] = entry
        if order is not None:
            diagnostic = _order_record(group.ids, order)
            if diagnostic is not None:
                record["order_diagnostic"] = diagnostic
        return record

    tree = _group_tree(items, dimensions=dimensions, labelled=labels is not None)
    return {**_settings_block(labels=labels, clusters=clusters, bootstrap=bootstrap, profile_ids=profile_ids, mode=mode),
            **({"excluded_exposed": dict(exclusions)} if exclusions is not None else {}), **_map_tree(tree, render)}


def _without_exposed(items: list[dict[str, Any]], exclusions: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if exclusions is None:
        return items
    excluded = set(exclusions["item_ids"])
    return [item for item in items if item["item_id"] not in excluded]


def paired_slice_report(base_items: list[dict[str, Any]], cand_items: list[dict[str, Any]], *, profile_ids: list[str],
                        labels: Mapping[str, Any] | None, clusters: Mapping[str, Any] | None,
                        bootstrap: Mapping[str, int] | None, mode: str = "page",
                        exclusions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Per-slice candidate-minus-baseline deltas over common items, with paired cluster intervals.

    ``exclusions`` (``exposure_exclusions`` over both sides) drops every item either model saw.
    """
    base = {item["item_id"]: item for item in _without_exposed(base_items, exclusions)}
    common = [item for item in _without_exposed(cand_items, exclusions) if item["item_id"] in base]
    cand = {item["item_id"]: item for item in common}
    cluster_map = clusters["clusters"] if clusters is not None else None
    dimensions = NODE_DIMENSIONS if labels is not None else sorted({key for item in common for key in item["strata"]})

    def render(group: _Group) -> dict[str, Any]:
        record, selected = _slice_header(group, profile_ids, cluster_map)
        record["profiles"] = {}
        for pid in selected:
            ids = [i for i in group.ids if pid in cand[i]["profiles"] and pid in base[i]["profiles"]]
            b_parts = [base[i]["profiles"][pid] for i in ids]
            c_parts = [cand[i]["profiles"][pid] for i in ids]
            b_agg, c_agg = _aggregate(b_parts), _aggregate(c_parts)
            entry: dict[str, Any] = {"items": len(ids)}
            for metric in ("cer", "wer"):
                entry[f"baseline_{metric}"], entry[f"candidate_{metric}"] = b_agg[metric], c_agg[metric]
                entry[f"delta_{metric}"] = (None if None in (b_agg[metric], c_agg[metric])
                                            else c_agg[metric] - b_agg[metric])
            if cluster_map is not None and bootstrap is not None:
                member_clusters = [cluster_map[i] for i in ids]
                count = len(set(member_clusters))
                entry["interval_clusters"], entry["interval_flags"] = count, cluster_flags(count)
                for metric, edits, units in (("cer", "character_edits", "reference_characters"),
                                             ("wer", "word_edits", "reference_words")):
                    interval = (None if count < TOO_FEW_CLUSTERS else
                                _bootstrap(_units(b_parts, edits, units), _units(c_parts, edits, units),
                                           member_clusters, bootstrap))
                    entry[f"delta_{metric}_ci"] = interval
                    # A low-cluster number is a separation only when its paired interval excludes 0.
                    entry[f"{metric}_separated"] = None if interval is None else (interval[0] > 0 or interval[1] < 0)
            record["profiles"][pid] = entry
        return record

    tree = _group_tree(common, dimensions=dimensions, labelled=labels is not None)
    return {**_settings_block(labels=labels, clusters=clusters, bootstrap=bootstrap, profile_ids=profile_ids, mode=mode),
            "paired": True, "common_item_count": len(common),
            **({"excluded_exposed": dict(exclusions)} if exclusions is not None else {}), **_map_tree(tree, render)}


# --- order diagnostic inputs ------------------------------------------------------------------------------------

def page_order_rows(report: Mapping[str, Any], predictions: Mapping[str, str],
                    references: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """Line-matched primary scores beside each page-order item's primary score (lines are not physical lines)."""
    profile = NORMALIZATION_PROFILES[PRIMARY_PROFILE_ID]
    rows = {}
    for item in report["items"]:
        item_id = item["item_id"]
        matched, stats = line_matched_prediction(predictions[item_id], references[item_id])
        rows[item_id] = {"page_order": item["profiles"][PRIMARY_PROFILE_ID],
                         "line_matched": _pair(profile.apply(matched), profile.apply(references[item_id])),
                         "reference_lines": stats["reference_lines"], "matched_lines": stats["matched_lines"],
                         "physical_lines": False}
    return rows


def within_line_rows(view: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Order rows for ``reading_order_verified: within_line`` items, from their as_is and line_matched.v1 reports."""
    as_is = {item["item_id"]: item for item in view["views"]["as_is"]["items"]}
    stats = {item["item_id"]: item for item in view["matching"]["items"]}
    rows = {}
    for item in view["views"][view["view_id"]]["items"]:
        item_id = item["item_id"]
        if item_id in as_is and item_id in stats:
            rows[item_id] = {"page_order": as_is[item_id]["profiles"][PRIMARY_PROFILE_ID],
                             "line_matched": item["profiles"][PRIMARY_PROFILE_ID],
                             "reference_lines": stats[item_id]["reference_lines"],
                             "matched_lines": stats[item_id]["matched_lines"], "physical_lines": True}
    return rows


# --- line-reference mode ----------------------------------------------------------------------------------------

def load_line_references(path: Path) -> dict[str, Any]:
    """Read a line_verify ``line_verify_line_references.v1`` line set; only adjudicated, eligible lines are scored."""
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageExecutionError(f"could not read line references {path.name}: {exc}") from exc
    where = f"line references {path.name}"
    if not isinstance(payload, dict) or payload.get("schema_version") != LINE_REFERENCES_SCHEMA:
        raise StageExecutionError(f"{where} must use schema_version {LINE_REFERENCES_SCHEMA}")
    lines = payload.get("lines")
    if not isinstance(lines, list) or not lines:
        raise StageExecutionError(f"{where} needs a non-empty lines list")
    texts, views, clusters, strata, excluded = {}, {}, {}, {}, []
    for line in lines:
        item_id = line.get("item_id") if isinstance(line, dict) else None
        if not isinstance(item_id, str) or not item_id or item_id in texts or item_id in {e["item_id"] for e in excluded}:
            raise StageExecutionError(f"{where}: each line needs a unique item_id")
        text, book, line_views = line.get("text"), line.get(LINE_CLUSTER_KEY), line.get("reference_views")
        if not isinstance(text, str) or not text.strip() or not isinstance(book, str) or not book:
            raise StageExecutionError(f"{where}: line {item_id} needs non-empty text and {LINE_CLUSTER_KEY}")
        if (not isinstance(line_views, list) or not line_views or not set(line_views) <= LINE_REFERENCE_VIEWS
                or "consonantal" not in line_views):
            raise StageExecutionError(f"{where}: line {item_id} reference_views must be a subset of "
                                      f"{sorted(LINE_REFERENCE_VIEWS)} that includes consonantal")
        if line.get("pointed_print") and "primary" in line_views:
            raise StageExecutionError(f"{where}: pointed_print line {item_id} may serve consonantal views only")
        if line.get("adjudication_status") != "adjudicated" or line.get("reference_eligible") is not True:
            excluded.append({"item_id": item_id, "reason": "line reference is not adjudicated and reference-eligible"})
            continue
        texts[item_id], views[item_id], clusters[item_id] = text, tuple(line_views), book
        strata[item_id] = {"source": str(line.get("source") or "unknown")}
    if not texts:
        raise StageExecutionError(f"{where} has no adjudicated, reference-eligible line")
    return {"texts": texts, "views": views, "clusters": {"cluster_key": LINE_CLUSTER_KEY, "clusters": clusters},
            "strata": strata, "excluded": excluded,
            "identity": {"kind": "line_verify_line_references", "schema_version": LINE_REFERENCES_SCHEMA,
                         "batch_id": payload.get("batch_id"), "sha256": hashlib.sha256(raw).hexdigest(),
                         "line_count": len(lines), "scored_line_count": len(texts)}}


def _line_profile_allowed(profile_id: str, views: tuple[str, ...]) -> bool:
    return "primary" in views or profile_id == CONSONANTAL_PROFILE_ID


def line_items(predictions: Mapping[str, str], lines: Mapping[str, Any], profile_ids: list[str],
               labels: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    resolved = [NORMALIZATION_PROFILES[pid] for pid in profile_ids]
    items = []
    for item_id in sorted(lines["texts"]):
        if item_id not in predictions:
            continue
        strata = dict(lines["strata"][item_id])
        if labels is not None:
            strata.update(labels["labels"][item_id])  # already flat (label_strata)
        items.append({"item_id": item_id, "strata": strata, "reference_views": list(lines["views"][item_id]),
                      "profiles": {p.profile_id: _pair(p.apply(predictions[item_id]), p.apply(lines["texts"][item_id]))
                                   for p in resolved if _line_profile_allowed(p.profile_id, lines["views"][item_id])}})
    return items


def line_reference_report(predictions: Mapping[str, str], lines: Mapping[str, Any], *, track: str,
                          profile_ids: list[str], labels: Mapping[str, Any] | None,
                          bootstrap: Mapping[str, int] | None,
                          model_ids: Mapping[str, str | None] | None = None) -> dict[str, Any]:
    """Score line_verify line references (spec §3a). Never mixed with page or line-aligned page numbers."""
    if labels is not None:
        require_labels(lines["texts"], labels["labels"], "line reference")
    if CONSONANTAL_PROFILE_ID not in profile_ids:
        raise StageExecutionError(f"--line-references needs the {CONSONANTAL_PROFILE_ID} profile: pointed_print lines "
                                  "are scored on consonantal views only")
    items = line_items(predictions, lines, profile_ids, labels)
    ids = sorted(lines["texts"])
    return {
        "reference_status": "adjudicated", "unit": "line", "track": track, "line_set": lines["identity"],
        "benchmark_line_count": len(ids), "evaluated_line_count": len(items),
        "missing_predictions": sorted(set(ids) - predictions.keys()),
        "unexpected_predictions": sorted(predictions.keys() - set(ids)),
        "excluded_lines": lines["excluded"],
        "view_rule": "a line whose reference_views are consonantal only (pointed_print) is scored on consonantal.v1 "
                     "only; every other profile is aggregated over the lines that also serve primary views",
        "measures": slice_report(items, profile_ids=profile_ids, labels=labels, clusters=lines["clusters"],
                                 bootstrap=bootstrap, mode="line",
                                 exclusions=exposure_exclusions(ids, labels, model_ids or {"scored": None})),
        "items": items,
    }


def paired_line_reference_report(base: Mapping[str, Any], cand: Mapping[str, Any], *, profile_ids: list[str],
                                 labels: Mapping[str, Any] | None, lines: Mapping[str, Any],
                                 bootstrap: Mapping[str, int] | None,
                                 model_ids: Mapping[str, str | None] | None = None) -> dict[str, Any]:
    exclusions = exposure_exclusions(lines["texts"], labels, model_ids or {"baseline": None, "candidate": None})
    return paired_slice_report(base["items"], cand["items"], profile_ids=profile_ids, labels=labels,
                               clusters=lines["clusters"], bootstrap=bootstrap, mode="line", exclusions=exclusions)


__all__ = [
    "EVAL_LABELS_SCHEMA", "NODES", "VERTICAL", "LINE_REFERENCES_SCHEMA", "NIQQUD_VALUES", "apply_label_strata",
    "cer_distribution", "cluster_flags", "exposure_exclusions", "line_reference_report", "load_eval_labels", "load_line_references",
    "paired_line_reference_report", "paired_slice_report", "require_labels", "slice_report",
]
