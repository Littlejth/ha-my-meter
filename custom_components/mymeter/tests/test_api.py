"""Tests for the mymeter API CSV parser."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

# Allow the integration package to be imported when running pytest standalone.
ROOT = None
for _p in Path(__file__).resolve().parents:
    if (_p / "custom_components").is_dir():
        ROOT = _p
        break
if ROOT is None:
    ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from custom_components.mymeter.api import parse_meters, parse_usage_csv
except Exception as exc:  # pylint: disable=broad-except
    parse_usage_csv = None
    parse_meters = None
    _IMPORT_ERROR = exc


SAMPLE = (
    'Start,Usage Direction,kWh\n'
    '"07/14/2025 12:00:00 AM","Delivered","36.28"\n'
    '"07/15/2025 12:00:00 AM","Delivered","41.34"\n'
)

# Minimal slice of the Dashboard meter-list markup (see RESEARCH.md §5.5):
# a checkbox named meterIds (its value encodes the internal id + rate) followed
# by <span id="meterId-NNNNN">DISPLAY</span>.
METER_HTML = (
    '<label><input type="checkbox" name="meterIds" '
    'aria-label="ToggleSwitch" '
    'value="[&quot;74352_0_&quot;_5_1_&quot;Rg-1 P&quot;_19217_Delivered&quot;]" '
    'checked /><span class="slider"></span></label>'
    '<span id="meterId-74352">4200010055</span>'
)


def test_parse_usage_csv_sample() -> None:
    """The parser returns one dict per row with the expected fields."""
    if parse_usage_csv is None:
        print(f"SKIP: could not import parsers: {_IMPORT_ERROR}")
        return
    rows = parse_usage_csv(SAMPLE)
    assert len(rows) == 2
    assert rows[0]["kwh"] == 36.28
    assert rows[1]["kwh"] == 41.34
    assert rows[0]["direction"] == "Delivered"
    assert rows[1]["direction"] == "Delivered"
    assert rows[0]["start"] == datetime.datetime(2025, 7, 14, 0, 0)
    assert rows[1]["start"] == datetime.datetime(2025, 7, 15, 0, 0)


def test_parse_meters_sample() -> None:
    """The meter parser maps the internal id and display number."""
    if parse_meters is None:
        print(f"SKIP: could not import parsers: {_IMPORT_ERROR}")
        return
    meters = parse_meters(METER_HTML)
    assert len(meters) == 1
    assert meters[0]["id"] == "74352"
    assert meters[0]["label"] == "4200010055"
    assert meters[0]["rate"] == "Rg-1 P"
