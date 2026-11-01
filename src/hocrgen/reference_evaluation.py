"""Reference-aware, offline text scoring; the E2a raw API remains unchanged."""
from __future__ import annotations

from collections import Counter
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
            output.append("".join(char for char, include in zip(line.text, mask) if include))
    return "\n".join(output)


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
