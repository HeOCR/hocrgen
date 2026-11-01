"""Reference-aware, offline text scoring; the E2a raw API remains unchanged."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, Mapping

from hocrgen.evaluation import levenshtein_distance
from hocrgen.manifests.models import BenchmarkTranscriptionReferenceRecord

# Deliberately finite: reference files use strings, not a closed enum.
_DECISIONS = {
    "include_primary_and_report": True,
    "include_readable_and_report": True,
    "include_primary": True,
    "exclude_primary": False,
    "include_when_ordered_else_separate": True,
}
_NEGATIONS = frozenset({"לא", "אין", "אינו", "אינה", "אינם", "אינן", "בלי", "בלתי"})
_NUMBER = re.compile(r"\d+(?:[.,:/\-]\d+)*", re.UNICODE)


def reference_text(record: BenchmarkTranscriptionReferenceRecord) -> str:
    """Return ordered, scoped text; reject ambiguity rather than infer a policy.

    Span decisions are applied to original code-point offsets, before NFC.
    Predictions must already be scoped to the same included content.
    """
    return "\n".join(
        "".join(char for char, include in zip(text, mask) if include) for text, mask in _line_masks(record)
    )


def _line_masks(record: BenchmarkTranscriptionReferenceRecord) -> list[tuple[str, list[bool]]]:
    """Validate a reference and return each ordered line with its per-code-point inclusion mask."""
    if record.review.status not in {"reviewed", "adjudicated"}:
        raise ValueError("reference must be reviewed or adjudicated")
    pages = sorted(record.pages, key=lambda p: p.reading_order)
    if len({p.page_id for p in pages}) != len(pages) or len({p.reading_order for p in pages}) != len(pages):
        raise ValueError("duplicate page id or reading order")
    for value in record.scoring_policy.values():
        if value not in _DECISIONS:
            raise ValueError(f"unsupported scoring policy: {value}")
    if len({span.span_id for span in record.spans}) != len(record.spans):
        raise ValueError("duplicate span id")
    output = []
    for page in pages:
        lines = sorted((line for line in record.lines if line.page_id == page.page_id), key=lambda line: line.reading_order)
        if not lines or len({line.reading_order for line in lines}) != len(lines):
            raise ValueError("missing lines or duplicate line reading order")
        for line in lines:
            mask = [True] * len(line.text)
            applied: dict[int, bool] = {}
            for span in (span for span in record.spans if span.line_id == line.line_id):
                if span.status not in record.scoring_policy or span.scoring not in _DECISIONS:
                    raise ValueError("unsupported span status or scoring decision")
                decision = _DECISIONS[span.scoring]
                if decision != _DECISIONS[record.scoring_policy[span.status]]:
                    raise ValueError("span decision conflicts with scoring policy")
                for offset in range(span.start, span.end):
                    if offset in applied and applied[offset] != decision:
                        raise ValueError("overlapping spans have conflicting decisions")
                    applied[offset] = decision
                    mask[offset] = decision
            output.append((line.text, mask))
    return output


def _pair(prediction: str, reference: str) -> dict:
    chars = levenshtein_distance(prediction, reference)
    predicted_words, reference_words = prediction.split(), reference.split()
    words = levenshtein_distance(predicted_words, reference_words)
    pn, rn = _NUMBER.findall(prediction), _NUMBER.findall(reference)
    punctuation = '.,:;!?()[]{}"\'׳״'
    pneg = [token for word in predicted_words if (token := word.strip(punctuation)) in _NEGATIONS]
    rneg = [token for word in reference_words if (token := word.strip(punctuation)) in _NEGATIONS]
    return {
        "character_edits": chars, "reference_characters": len(reference),
        "cer": chars / len(reference) if reference else None,
        "word_edits": words, "reference_words": len(reference_words),
        "wer": words / len(reference_words) if reference_words else None,
        "exact_match": prediction == reference,
        "diagnostics": {
            "number_tokens_match": pn == rn,
            "negation_tokens_match": pneg == rneg,
            "same_word_multiset_different_order": predicted_words != reference_words and Counter(predicted_words) == Counter(reference_words),
        },
    }


def _span_report(record: BenchmarkTranscriptionReferenceRecord) -> dict:
    statuses: dict[str, list[str]] = {}
    for span in record.spans:
        statuses.setdefault(span.status, []).append(span.span_id)
    return {status: {"count": len(ids), "span_ids": sorted(ids)} for status, ids in sorted(statuses.items())}


def evaluate_reference_predictions(
    item_ids: Iterable[str], *, predictions: Mapping[str, str],
    references: Mapping[str, BenchmarkTranscriptionReferenceRecord], normalize_nfc: bool = False,
) -> dict:
    """Score explicit item IDs, reporting raw metrics separately from optional NFC."""
    ids = list(item_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate benchmark item id")
    missing_predictions = sorted(set(ids) - predictions.keys())
    missing_references = sorted(set(ids) - references.keys())
    scoped_references = {}
    for item_id in sorted(set(ids) & references.keys()):
        record = references[item_id]
        if record.item_id != item_id:
            raise ValueError("reference item id mismatch")
        scoped_references[item_id] = reference_text(record)
    items = []
    for item_id in sorted(set(ids) & predictions.keys() & references.keys()):
        reference = scoped_references[item_id]
        prediction = predictions[item_id]
        result = {"item_id": item_id, "reference_spans": _span_report(references[item_id]),
                  "raw": _pair(prediction, reference)}
        if normalize_nfc:
            result["nfc"] = _pair(unicodedata.normalize("NFC", prediction), unicodedata.normalize("NFC", reference))
        items.append(result)
    def aggregate(key: str) -> dict:
        parts = [item[key] for item in items]
        ce = sum(p["character_edits"] for p in parts)
        rc = sum(p["reference_characters"] for p in parts)
        we = sum(p["word_edits"] for p in parts)
        rw = sum(p["reference_words"] for p in parts)
        return {"character_edits": ce, "reference_characters": rc, "cer": ce / rc if rc else None,
                "word_edits": we, "reference_words": rw, "wer": we / rw if rw else None}
    report = {
        "benchmark_item_count": len(ids), "evaluated_item_count": len(items),
        "missing_predictions": missing_predictions, "missing_references": missing_references,
        "unexpected_predictions": sorted(predictions.keys() - set(ids)),
        "unexpected_references": sorted(references.keys() - set(ids)),
        "prediction_coverage": (len(ids) - len(missing_predictions)) / len(ids) if ids else None,
        "reference_coverage": (len(ids) - len(missing_references)) / len(ids) if ids else None,
        "scoring_scope": "predictions must already exclude reference-excluded content; text must be in logical order",
        "diagnostic_limit": "literal token comparisons only; not semantic correctness",
        "raw": aggregate("raw"), "items": items,
    }
    if normalize_nfc:
        report["nfc"] = aggregate("nfc")
    return report


def score_unreviewed_text_pair(*, prediction: str, reference: str, normalize_nfc: bool = False) -> dict:
    """Score user-supplied text for diagnostics, without claiming benchmark status."""
    result = {
        "reference_status": "unreviewed",
        "benchmark_ready": False,
        "scoring_scope": "caller supplies comparable content in logical order; no span policy is inferred",
        "diagnostic_limit": "literal token comparisons only; not semantic correctness",
        "raw": _pair(prediction, reference),
    }
    if normalize_nfc:
        result["nfc"] = _pair(unicodedata.normalize("NFC", prediction), unicodedata.normalize("NFC", reference))
    return result


def assemble_page_predictions(
    pages: Mapping[str, str], *, item_pages: Mapping[str, list[str]],
) -> dict[str, str]:
    """Assemble raw engine page texts using an explicit item-to-ordered-page mapping.

    Page IDs are opaque; this function does not infer identity from image digests.
    """
    used: set[str] = set()
    assembled = {}
    for item_id, ordered_pages in item_pages.items():
        if not item_id or not ordered_pages:
            raise ValueError("each item needs an id and at least one page")
        for page_id in ordered_pages:
            if page_id in used:
                raise ValueError("page mapped more than once")
            if page_id not in pages:
                raise ValueError("mapped page prediction missing")
            used.add(page_id)
        assembled[item_id] = "\n".join(pages[page_id] for page_id in ordered_pages)
    if used != pages.keys():
        raise ValueError("unmapped page prediction")
    return assembled


# --- E2c3: versioned normalization profiles, strata and the alignment-masked diagnostic ---------------

_BIDI_CONTROLS = frozenset(
    {"‎", "‏", "؜", *(chr(c) for c in range(0x202A, 0x202F)), *(chr(c) for c in range(0x2066, 0x206A))}
)
# Hebrew cantillation (te'amim) and points (niqqud, dagesh, shin/sin dots, meteg, qamats qatan). Maqaf, paseq and
# sof pasuq are punctuation and are left to punct_folded.
_HEBREW_MARKS = frozenset(
    {*(chr(c) for c in range(0x0591, 0x05B0)), *(chr(c) for c in range(0x05B0, 0x05BE)),
     "ֿ", "ׁ", "ׂ", "ׄ", "ׅ", "ׇ"}
)
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _strip_bidi_controls(text: str) -> str:
    return "".join(char for char in text if char not in _BIDI_CONTROLS)


def _fold_whitespace(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line for line in (_HORIZONTAL_SPACE.sub(" ", raw).strip() for raw in lines) if line)


def _strip_hebrew_marks(text: str) -> str:
    return "".join(char for char in text if char not in _HEBREW_MARKS)


def _fold_punctuation(text: str) -> str:
    folded = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Pd":
            folded.append(" ")
        elif not category.startswith("P"):
            folded.append(char)
    return "".join(folded)


_TRANSFORMS = {
    "nfc": _nfc,
    "strip_bidi_controls": _strip_bidi_controls,
    "fold_whitespace": _fold_whitespace,
    "strip_hebrew_marks": _strip_hebrew_marks,
    "fold_punctuation": _fold_punctuation,
}


@dataclass(frozen=True)
class NormalizationProfile:
    """A named, versioned transform chain applied identically to prediction and reference."""

    profile_id: str
    role: str
    transforms: tuple[str, ...]
    description: str

    def apply(self, text: str) -> str:
        for name in self.transforms:
            text = _TRANSFORMS[name](text)
        return text

    def describe(self) -> dict:
        return {"profile_id": self.profile_id, "role": self.role, "transforms": list(self.transforms),
                "description": self.description}


_PRIMARY_TRANSFORMS = ("nfc", "strip_bidi_controls", "fold_whitespace")
NORMALIZATION_PROFILES = {
    profile.profile_id: profile
    for profile in (
        NormalizationProfile("raw.v1", "baseline", (), "Unmodified code points."),
        NormalizationProfile("nfc.v1", "baseline", ("nfc",), "Unicode NFC composition only."),
        NormalizationProfile(
            "primary.v1", "primary", _PRIMARY_TRANSFORMS,
            "NFC; strip LRM/RLM/ALM, embeddings, overrides and isolates; fold horizontal whitespace runs to one "
            "space, trim lines, unify CR/CRLF to LF and drop empty lines.",
        ),
        NormalizationProfile(
            "consonantal.v1", "reported", (*_PRIMARY_TRANSFORMS, "strip_hebrew_marks", "nfc"),
            "primary.v1, then remove Hebrew niqqud and cantillation marks; reported alongside primary.",
        ),
        NormalizationProfile(
            "punct_folded.v1", "report_only", (*_PRIMARY_TRANSFORMS, "fold_punctuation", "fold_whitespace"),
            "primary.v1, then replace dash punctuation (including maqaf) with a space and delete all other "
            "punctuation (including geresh, gershayim and sof pasuq); never a headline score.",
        ),
    )
}
PRIMARY_PROFILE_ID = "primary.v1"
DEFAULT_PROFILE_IDS = tuple(NORMALIZATION_PROFILES)
STRATA_DIMENSIONS = ("language_script", "modality", "source_id", "document_type", "reference_origin")
MODALITIES = frozenset({"printed", "handwritten", "synthetic", "unknown"})


def _aggregate(parts: list[dict]) -> dict:
    ce = sum(p["character_edits"] for p in parts)
    rc = sum(p["reference_characters"] for p in parts)
    we = sum(p["word_edits"] for p in parts)
    rw = sum(p["reference_words"] for p in parts)
    return {"item_count": len(parts), "character_edits": ce, "reference_characters": rc, "cer": ce / rc if rc else None,
            "word_edits": we, "reference_words": rw, "wer": we / rw if rw else None}


def _resolve_profiles(profile_ids: Iterable[str]) -> list[NormalizationProfile]:
    ids = list(profile_ids)
    unknown = sorted(set(ids) - NORMALIZATION_PROFILES.keys())
    if unknown:
        raise ValueError(f"unknown normalization profile: {', '.join(unknown)}")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate normalization profile")
    if PRIMARY_PROFILE_ID not in ids:
        raise ValueError(f"{PRIMARY_PROFILE_ID} must be evaluated")
    return [NORMALIZATION_PROFILES[profile_id] for profile_id in ids]


def _item_strata(record: BenchmarkTranscriptionReferenceRecord, supplied: Mapping[str, str] | None) -> dict[str, str]:
    supplied = dict(supplied or {})
    unknown = sorted(set(supplied) - set(STRATA_DIMENSIONS))
    if unknown:
        raise ValueError(f"unknown stratum dimension: {', '.join(unknown)}")
    strata = {
        "language_script": "+".join(f"{entry.language}-{entry.script}" for entry in record.language_scripts),
        "modality": "unknown",
        "source_id": record.source_id,
        "document_type": "unknown",
        "reference_origin": "unknown",
    }
    strata.update({key: str(value) for key, value in supplied.items() if value not in (None, "")})
    if strata["modality"] not in MODALITIES:
        raise ValueError(f"unsupported modality: {strata['modality']}")
    return strata


def evaluate_reference_profiles(
    item_ids: Iterable[str], *, predictions: Mapping[str, str],
    references: Mapping[str, BenchmarkTranscriptionReferenceRecord],
    profiles: Iterable[str] = DEFAULT_PROFILE_IDS,
    item_strata: Mapping[str, Mapping[str, str]] | None = None,
    alignment_masked: bool = False,
) -> dict:
    """Score explicit item IDs under each named profile, with per-stratum aggregates.

    Every profile is applied to both prediction and scoped reference. ``primary.v1`` is the headline score;
    ``punct_folded.v1`` is report-only. The optional alignment-masked diagnostic is reported separately and
    never contributes to any profile score.
    """
    resolved = _resolve_profiles(profiles)
    ids = list(item_ids)
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate benchmark item id")
    unexpected_strata = sorted((item_strata or {}).keys() - set(ids))
    if unexpected_strata:
        raise ValueError(f"strata supplied for unknown item: {', '.join(unexpected_strata)}")
    missing_predictions = sorted(set(ids) - predictions.keys())
    missing_references = sorted(set(ids) - references.keys())
    scoped: dict[str, str] = {}
    for item_id in sorted(set(ids) & references.keys()):
        if references[item_id].item_id != item_id:
            raise ValueError("reference item id mismatch")
        scoped[item_id] = reference_text(references[item_id])
    items = []
    for item_id in sorted(set(ids) & predictions.keys() & references.keys()):
        record = references[item_id]
        items.append({
            "item_id": item_id,
            "strata": _item_strata(record, (item_strata or {}).get(item_id)),
            "reference_spans": _span_report(record),
            "profiles": {
                profile.profile_id: _pair(profile.apply(predictions[item_id]), profile.apply(scoped[item_id]))
                for profile in resolved
            },
        })
    strata: dict[str, dict[str, dict]] = {}
    for dimension in STRATA_DIMENSIONS:
        values = sorted({item["strata"][dimension] for item in items})
        strata[dimension] = {
            value: {
                profile.profile_id: _aggregate(
                    [item["profiles"][profile.profile_id] for item in items if item["strata"][dimension] == value]
                )
                for profile in resolved
            }
            for value in values
        }
    report = {
        "normalization_profiles": [profile.describe() for profile in resolved],
        "primary_profile": PRIMARY_PROFILE_ID,
        "report_only_profiles": [profile.profile_id for profile in resolved if profile.role == "report_only"],
        "benchmark_item_count": len(ids), "evaluated_item_count": len(items),
        "missing_predictions": missing_predictions, "missing_references": missing_references,
        "unexpected_predictions": sorted(predictions.keys() - set(ids)),
        "unexpected_references": sorted(references.keys() - set(ids)),
        "prediction_coverage": (len(ids) - len(missing_predictions)) / len(ids) if ids else None,
        "reference_coverage": (len(ids) - len(missing_references)) / len(ids) if ids else None,
        "scoring_scope": "predictions must already exclude reference-excluded content; text must be in logical order",
        "diagnostic_limit": "literal token comparisons only; not semantic correctness",
        "profiles": {
            profile.profile_id: _aggregate([item["profiles"][profile.profile_id] for item in items])
            for profile in resolved
        },
        "strata": strata,
        "items": items,
    }
    if alignment_masked:
        report["diagnostics"] = {"alignment_masked": evaluate_alignment_masked(
            sorted(set(ids) & predictions.keys() & references.keys()),
            predictions=predictions, references=references,
        )}
    return report


def _align(reference: str, prediction: str, max_cells: int) -> list[tuple[str, int, int | None]]:
    """Deterministic Levenshtein alignment.

    Returns ``(operation, reference_position, prediction_index)`` steps in order, where operation is ``"pair"``
    (match or substitution of ``reference[reference_position]``), ``"delete"`` (reference character with no
    prediction counterpart) or ``"insert"`` (prediction character placed before ``reference_position``).
    """
    n, m = len(reference), len(prediction)
    if (n + 1) * (m + 1) > max_cells:
        raise ValueError("alignment exceeds max_cells")
    previous = list(range(m + 1))
    moves = [bytearray(m + 1) for _ in range(n + 1)]  # 0 pair, 1 delete, 2 insert
    for j in range(1, m + 1):
        moves[0][j] = 2
    for i in range(1, n + 1):
        current = [i] + [0] * m
        moves[i][0] = 1
        for j in range(1, m + 1):
            diagonal = previous[j - 1] + (reference[i - 1] != prediction[j - 1])
            delete = previous[j] + 1
            insert = current[j - 1] + 1
            best = min(diagonal, delete, insert)
            current[j] = best
            moves[i][j] = 0 if best == diagonal else (1 if best == delete else 2)
        previous = current
    steps: list[tuple[str, int, int | None]] = []
    i, j = n, m
    while i or j:
        move = moves[i][j]
        if move == 0:
            i, j = i - 1, j - 1
            steps.append(("pair", i, j))
        elif move == 1:
            i -= 1
            steps.append(("delete", i, None))
        else:
            j -= 1
            steps.append(("insert", i, j))
    steps.reverse()
    return steps


def alignment_masked_prediction(
    record: BenchmarkTranscriptionReferenceRecord, prediction: str, *, max_cells: int = 4_000_000,
) -> tuple[str, dict]:
    """Remove prediction characters that align to reference-excluded spans of the full, unscoped reference.

    Diagnostic only: the alignment is heuristic and can mis-attribute characters near span boundaries.
    """
    full_chars: list[str] = []
    mask: list[bool] = []
    for index, (text, line_mask) in enumerate(_line_masks(record)):
        if index:
            full_chars.append("\n")
            mask.append(True)
        full_chars.extend(text)
        mask.extend(line_mask)
    excluded = mask.count(False)
    stats = {"excluded_reference_characters": excluded, "removed_prediction_characters": 0}
    if not excluded:
        return prediction, stats
    n = len(mask)
    kept: list[str] = []
    for operation, position, pred_index in _align("".join(full_chars), prediction, max_cells):
        if pred_index is None:
            continue
        if operation == "pair":
            keep = mask[position]
        else:
            left_excluded = position > 0 and not mask[position - 1]
            right_excluded = position < n and not mask[position]
            # Drop an insertion only when it sits inside, or at the document edge of, an excluded run.
            keep = not ((left_excluded or position == 0) and (right_excluded or position == n)
                        and (left_excluded or right_excluded))
        if keep:
            kept.append(prediction[pred_index])
    stats["removed_prediction_characters"] = len(prediction) - len(kept)
    return "".join(kept), stats


def evaluate_alignment_masked(
    item_ids: Iterable[str], *, predictions: Mapping[str, str],
    references: Mapping[str, BenchmarkTranscriptionReferenceRecord],
    profile: str = PRIMARY_PROFILE_ID, max_cells: int = 4_000_000,
) -> dict:
    """Diagnostic scoring of unscoped full-page predictions after alignment-based masking.

    The result is labelled ``diagnostic_only`` and ``primary_eligible: false``; callers must never merge it
    into primary or profile scores.
    """
    normalizer = _resolve_profiles([profile, PRIMARY_PROFILE_ID] if profile != PRIMARY_PROFILE_ID else [profile])[0]
    items, skipped = [], []
    for item_id in item_ids:
        record = references[item_id]
        try:
            masked, stats = alignment_masked_prediction(record, predictions[item_id], max_cells=max_cells)
        except ValueError as exc:
            skipped.append({"item_id": item_id, "reason": str(exc)})
            continue
        items.append({"item_id": item_id, **stats,
                      "score": _pair(normalizer.apply(masked), normalizer.apply(reference_text(record)))})
    return {
        "mode": "alignment_masked",
        "diagnostic_only": True,
        "primary_eligible": False,
        "profile": normalizer.profile_id,
        "limitation": "heuristic edit-distance alignment against the unscoped reference; boundary characters may "
                      "be mis-attributed; never a substitute for scoped predictions",
        "aggregate": _aggregate([item["score"] for item in items]),
        "items": items,
        "skipped": skipped,
    }
