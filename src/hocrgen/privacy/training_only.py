"""Training-only release scope for Knesset committee protocols (decision 2026-11-11, item 1).

Committee protocols from 1976 on may enter training lists, but their line crops, page
images and transcriptions never enter a published dataset, glyph bank, benchmark or any
other released artefact. A protocol of year *Y* is publishable from 1 January of
*Y* + 51 (state copyright: 50 years from creation, ending on 31 December), so the scope is
derived from the session date, never fixed.

Every committee line row carries ``release_scope``. :func:`refuse_training_only_release`
runs in the release export and stops it on any training-only row, and on any committee
row whose scope cannot be derived (no session date): it fails closed.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable, Mapping

DECISION_PATH = "planning/decisions/2026-11-11-knesset-protocols-training-vs-release.md"
TRAINING_ONLY = "training_only"
PUBLISHABLE = "publishable"
COMMITTEE_SOURCE_PREFIX = "knesset_committee"
COMMITTEE_UNIT_PREFIX = "committee:"
_YEAR = re.compile(r"^(\d{4})")


class TrainingOnlyReleaseError(ValueError):
    """Raised when training-only material reaches a release."""


def _get(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        value = row.get(name)
        if value is None and isinstance(row.get("metadata"), Mapping):
            value = row["metadata"].get(name)
        return value
    value = getattr(row, name, None)
    metadata = getattr(row, "metadata", None)
    if value is None and isinstance(metadata, Mapping):
        value = metadata.get(name)
    return value


def committee_release_scope(session_date: str | date | None, *, today: date | None = None) -> str:
    """``publishable`` only when the session's year *Y* satisfies today >= 1 January *Y* + 51."""

    if session_date is None or session_date == "":
        return TRAINING_ONLY
    year = session_date.year if isinstance(session_date, date) else None
    if year is None:
        m = _YEAR.match(str(session_date).strip())
        if not m:
            return TRAINING_ONLY
        year = int(m.group(1))
    today = today or date.today()
    return PUBLISHABLE if today >= date(year + 51, 1, 1) else TRAINING_ONLY


def is_committee_row(row: Any) -> bool:
    source = str(_get(row, "source_id") or "")
    if source.startswith(COMMITTEE_SOURCE_PREFIX):
        return True
    return any(str(_get(row, name) or "").startswith(COMMITTEE_UNIT_PREFIX) for name in ("unit_id", "source_unit"))


def refuse_training_only_release(rows: Iterable[Any], *, today: date | None = None, builder: str = "release export") -> int:
    """Stop a release that holds training-only rows. Returns the number of rows checked.

    A row is refused when its ``release_scope`` (row or metadata) is ``training_only``, or
    when it is a committee row (``source_id`` starting ``knesset_committee`` or a
    ``committee:`` unit) whose ``session_date`` does not make it publishable today, even if
    it claims otherwise.
    """

    checked, refused = 0, []
    for row in rows:
        checked += 1
        scope = _get(row, "release_scope")
        bad = scope == TRAINING_ONLY
        if not bad and is_committee_row(row):
            bad = committee_release_scope(_get(row, "session_date"), today=today) != PUBLISHABLE
        if bad:
            refused.append(str(_get(row, "line_id") or _get(row, "item_id") or _get(row, "unit_id") or "?"))
    if refused:
        shown = ", ".join(refused[:10]) + (f" and {len(refused) - 10} more" if len(refused) > 10 else "")
        raise TrainingOnlyReleaseError(
            f"{builder}: {len(refused)} training-only row(s) cannot be released ({DECISION_PATH}): {shown}"
        )
    return checked
