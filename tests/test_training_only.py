from datetime import date

import pytest

from hocrgen.privacy.training_only import (
    PUBLISHABLE,
    TRAINING_ONLY,
    TrainingOnlyReleaseError,
    committee_release_scope,
    refuse_training_only_release,
)

TODAY = date(2026, 11, 13)


@pytest.mark.parametrize(
    "when,expected",
    [
        ("1975-12-31", PUBLISHABLE),
        ("1976-01-01", TRAINING_ONLY),
        ("2008-05-25", TRAINING_ONLY),
        (date(1960, 3, 1), PUBLISHABLE),
        (None, TRAINING_ONLY),
        ("unknown", TRAINING_ONLY),
    ],
)
def test_scope_from_session_date(when, expected):
    assert committee_release_scope(when, today=TODAY) == expected


def test_scope_rolls_forward_each_year():
    assert committee_release_scope("1976-06-01", today=date(2026, 12, 31)) == TRAINING_ONLY
    assert committee_release_scope("1976-06-01", today=date(2027, 1, 1)) == PUBLISHABLE


def test_release_refuses_training_only_rows():
    rows = [
        {"line_id": "a", "source_id": "knesset_plenary_k13_25"},
        {"line_id": "b", "unit_id": "committee:K24_607800", "session_date": "2021-11-02"},
    ]
    with pytest.raises(TrainingOnlyReleaseError, match="1 training-only"):
        refuse_training_only_release(rows, today=TODAY)


def test_committee_row_claiming_publishable_is_still_refused():
    row = {"line_id": "c", "source_id": "knesset_committee_protocols_k16plus", "release_scope": PUBLISHABLE,
           "session_date": "2010-01-01"}
    with pytest.raises(TrainingOnlyReleaseError):
        refuse_training_only_release([row], today=TODAY)


def test_committee_row_without_date_fails_closed_and_marker_in_metadata():
    with pytest.raises(TrainingOnlyReleaseError):
        refuse_training_only_release([{"line_id": "d", "unit_id": "committee:K16_1"}], today=TODAY)
    with pytest.raises(TrainingOnlyReleaseError):
        refuse_training_only_release([{"line_id": "e", "metadata": {"release_scope": TRAINING_ONLY}}], today=TODAY)


def test_old_committee_and_other_rows_pass():
    rows = [{"line_id": "f", "unit_id": "committee:K8_9", "session_date": "1974-02-01"}, {"line_id": "g"}]
    assert refuse_training_only_release(rows, today=TODAY) == 2


def test_pre1976_scanned_committee_source_is_not_governed():
    row = {"item_id": "knesset_committee_protocols_pre1976:knesset_committee_399388__p0002",
           "source_id": "knesset_committee_protocols_pre1976"}
    assert refuse_training_only_release([row], today=TODAY) == 1
