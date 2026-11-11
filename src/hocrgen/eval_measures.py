"""E2e3: the pending decision-0017 measures, computed per item and aggregated per ``eval_slices`` slice.

- **Line-aligned pages** (spec §3b): for items whose reference lines are physical lines
  (``reading_order_verified: within_line``), reference and prediction lines are paired with the ``line_matched.v1``
  pairing. Per profile, the exact-line rate is the share of reference lines with an exact paired prediction line, and
  line CER is the micro CER over reference lines, where an unpaired reference line is a miss that costs its full
  characters.
- **Letter-level decomposition** (spec §1, diagnostic): Hebrew letters only (U+05D0-U+05EA, final forms included).
  Both sides are reduced to their letters after NFC, aligned by Levenshtein, and the substitutions, deletions and
  insertions are counted per reference letter. Marks, punctuation, digits, Latin and spaces never count.
- **Missed-region cost** (spec §4, diagnostic): on physical-line pages, the share of reference characters in unpaired
  reference lines (``primary.v1``); on paragraph references, the share of reference letters in deletion runs of at least
  20 letters, from the same letter alignment.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Iterable, Mapping

from hocrgen.evaluation import levenshtein_distance
from hocrgen.reference_evaluation import NORMALIZATION_PROFILES, PRIMARY_PROFILE_ID, _align, pair_lines

HEBREW_LETTER_FIRST, HEBREW_LETTER_LAST = "א", "ת"
DELETION_RUN_LETTERS = 20
LETTER_MAX_CELLS = 25_000_000
UNPAIRED_LINES = "unpaired_reference_lines"
DELETION_RUNS = f"deletion_runs_of_{DELETION_RUN_LETTERS}_or_more_letters"


def hebrew_letters(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFC", text) if HEBREW_LETTER_FIRST <= char <= HEBREW_LETTER_LAST)


def letter_edits(prediction: str, reference: str, *, max_cells: int = LETTER_MAX_CELLS) -> dict[str, Any]:
    """Letter-only substitution, deletion and insertion counts, and letters in long deletion runs."""
    reference_letters, predicted_letters = hebrew_letters(reference), hebrew_letters(prediction)
    counts = {"reference_letters": len(reference_letters), "substitutions": 0, "deletions": 0, "insertions": 0,
              "deletion_run_letters": 0, "skipped": False}
    try:
        steps = _align(reference_letters, predicted_letters, max_cells)
    except ValueError:
        return {**counts, "skipped": True}
    run = 0
    for operation, position, pred_index in steps:
        if operation == "delete":
            counts["deletions"] += 1
            run += 1
            continue
        if run >= DELETION_RUN_LETTERS:
            counts["deletion_run_letters"] += run
        run = 0
        if operation == "pair" and reference_letters[position] != predicted_letters[pred_index]:
            counts["substitutions"] += 1
        elif operation == "insert":
            counts["insertions"] += 1
    if run >= DELETION_RUN_LETTERS:
        counts["deletion_run_letters"] += run
    return counts


def line_aligned(prediction: str, reference: str, profile_ids: Iterable[str]) -> dict[str, dict[str, int]]:
    """Per-profile exact-line and line-CER counts over the reference's physical lines (``line_matched.v1`` pairs)."""
    reference_lines, prediction_lines, pairs = pair_lines(prediction, reference)
    stats = {}
    for profile_id in profile_ids:
        profile = NORMALIZATION_PROFILES[profile_id]
        row = {"reference_lines": 0, "exact_lines": 0, "missed_lines": 0, "line_edits": 0, "reference_characters": 0,
               "missed_characters": 0}
        for r_index, r_line in enumerate(reference_lines):
            normalized = profile.apply(r_line)
            if not normalized:
                continue
            row["reference_lines"] += 1
            row["reference_characters"] += len(normalized)
            if r_index not in pairs:
                row["missed_lines"] += 1
                row["missed_characters"] += len(normalized)
                row["line_edits"] += len(normalized)
                continue
            predicted = profile.apply(prediction_lines[pairs[r_index]])
            row["line_edits"] += levenshtein_distance(predicted, normalized)
            row["exact_lines"] += predicted == normalized
        stats[profile_id] = row
    return stats


def item_measures(prediction: str, reference: str, *, profile_ids: Iterable[str], physical_lines: bool,
                  letters_prediction: str | None = None) -> dict[str, Any]:
    """The E2e3 per-item inputs. ``letters_prediction`` overrides the text used for the letter alignment (for
    line-ordered items, the ``line_matched.v1`` prediction, so block order is not counted as deletions)."""
    measures: dict[str, Any] = {"letters": letter_edits(letters_prediction if letters_prediction is not None
                                                        else prediction, reference)}
    if physical_lines:
        measures["line_aligned"] = line_aligned(prediction, reference, profile_ids)
    return measures


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def line_aligned_entry(rows: list[Mapping[str, int]]) -> dict[str, Any]:
    total = {key: sum(row[key] for row in rows) for key in
             ("reference_lines", "exact_lines", "missed_lines", "line_edits", "reference_characters")}
    return {"items": len(rows), **total, "exact_line_rate": _rate(total["exact_lines"], total["reference_lines"]),
            "line_cer": _rate(total["line_edits"], total["reference_characters"]),
            "missed_line_rate": _rate(total["missed_lines"], total["reference_lines"]),
            "method": "line_matched.v1 pairing; an unpaired reference line is a miss costing its full characters"}


def letter_record(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    used = [row for row in rows if not row["skipped"]]
    letters = sum(row["reference_letters"] for row in used)
    counts = {key: sum(row[key] for row in used) for key in ("substitutions", "deletions", "insertions")}
    return {"diagnostic_only": True, "alphabet": "Hebrew letters U+05D0-U+05EA (final forms included)",
            "items": len(used), "skipped_items": len(rows) - len(used), "reference_letters": letters, **counts,
            "substitution_rate": _rate(counts["substitutions"], letters),
            "deletion_rate": _rate(counts["deletions"], letters),
            "insertion_rate": _rate(counts["insertions"], letters)}


def missed_region_record(rows: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    physical = [row for row in rows if "line_aligned" in row and PRIMARY_PROFILE_ID in row["line_aligned"]]
    if physical:
        missed = sum(row["line_aligned"][PRIMARY_PROFILE_ID]["missed_characters"] for row in physical)
        total = sum(row["line_aligned"][PRIMARY_PROFILE_ID]["reference_characters"] for row in physical)
        return {"diagnostic_only": True, "method": UNPAIRED_LINES, "profile": PRIMARY_PROFILE_ID,
                "items": len(physical), "missed_characters": missed, "reference_characters": total,
                "missed_region_cost": _rate(missed, total)}
    used = [row["letters"] for row in rows if not row["letters"]["skipped"]]
    if not used:
        return None
    missed = sum(row["deletion_run_letters"] for row in used)
    total = sum(row["reference_letters"] for row in used)
    return {"diagnostic_only": True, "method": DELETION_RUNS, "items": len(used), "missed_letters": missed,
            "reference_letters": total, "missed_region_cost": _rate(missed, total)}
