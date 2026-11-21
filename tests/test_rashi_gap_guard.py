"""Geometry checks for the optional training-crop gap guard."""
import pytest

from hocrgen.tools import benyehuda_nli_lines as lines


def word(left, right):
    return ("טקסט", 95.0, (left, 10, right, 20))


def test_wide_gap_flags_a_margin_merged_into_a_line_box():
    assert lines.suspicious_horizontal_gap([word(120, 140), word(40, 60), word(65, 90)], 10, 2)
    assert not lines.suspicious_horizontal_gap([word(40, 60), word(65, 90)], 10, 2)
    assert not lines.suspicious_horizontal_gap([word(40, 80), word(50, 60), word(85, 90)], 10, 2)


def test_missing_or_invalid_geometry_fails_closed():
    assert lines.suspicious_horizontal_gap([], 10, 2)
    assert lines.suspicious_horizontal_gap([word(10, 20)], 0, 2)
    assert lines.suspicious_horizontal_gap([word(20, 10)], 10, 2)


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_invalid_threshold_fails_before_reading_a_root(tmp_path, value):
    with pytest.raises(SystemExit, match="positive finite"):
        lines.main(["build", str(tmp_path / "out"), "--root", str(tmp_path / "missing"), "--reject-gap-ratio", value])
