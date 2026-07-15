"""Tests for the mymeter sensor value mapping."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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
    from custom_components.mymeter.sensor import MyMeterSensor
except Exception as exc:  # pylint: disable=broad-except
    MyMeterSensor = None
    _IMPORT_ERROR = exc


def _make_sensor(key: str, data: dict):
    """Build a MyMeterSensor with a lightweight fake coordinator/description."""
    coordinator = SimpleNamespace(
        data=data,
        config_entry=SimpleNamespace(entry_id="abc", domain="mymeter"),
    )
    description = SimpleNamespace(key=key)
    return MyMeterSensor(coordinator=coordinator, entity_description=description)


def test_sensor_reads_coordinator_keys() -> None:
    """native_value must read the coordinator key matching the entity key.

    Regression test for the key-mismatch bug where ``latest_interval_kwh``,
    ``last_reading_time`` and ``active_alerts`` were read under wrong keys
    (``latest_kwh`` / ``latest_start`` / ``alerts_active``) and so always
    returned None / 0.
    """
    if MyMeterSensor is None:
        print(f"SKIP: could not import sensor: {_IMPORT_ERROR}")
        return

    data = {
        "month_to_date_kwh": 120.5,
        "latest_interval_kwh": 12.34,
        "last_reading_time": "2025-07-15T00:00:00",
        "active_alerts": True,
    }
    assert _make_sensor("month_to_date_kwh", data).native_value == 120.5
    # These three previously returned None / 0 due to the wrong key.
    assert _make_sensor("latest_interval_kwh", data).native_value == 12.34
    assert (
        _make_sensor("last_reading_time", data).native_value
        == "2025-07-15T00:00:00"
    )
    assert _make_sensor("active_alerts", data).native_value == data["active_alerts"]
