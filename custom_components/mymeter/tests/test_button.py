"""Tests for the mymeter force-refresh button."""

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
    from custom_components.mymeter.button import MyMeterRefreshButton
except Exception as exc:  # pylint: disable=broad-except
    MyMeterRefreshButton = None
    _IMPORT_ERROR = exc


def _make_button() -> "MyMeterRefreshButton":
    """Build a refresh button with a fake coordinator that records refreshes."""
    calls: list[object] = []

    async def _request_refresh() -> None:
        calls.append(True)

    coordinator = SimpleNamespace(
        async_request_refresh=_request_refresh,
        config_entry=SimpleNamespace(entry_id="abc", domain="mymeter"),
    )
    button = MyMeterRefreshButton(coordinator=coordinator)
    button._refresh_calls = calls  # type: ignore[attr-defined]
    return button


async def test_refresh_button_requests_coordinator_refresh() -> None:
    """Pressing the button must trigger a coordinator refresh."""
    if MyMeterRefreshButton is None:
        print(f"SKIP: could not import button: {_IMPORT_ERROR}")
        return

    button = _make_button()
    assert button._refresh_calls == []  # type: ignore[attr-defined]
    await button.async_press()
    assert button._refresh_calls == [True]  # type: ignore[attr-defined]
