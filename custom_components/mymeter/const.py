"""Constants for the mymeter integration."""

import traceback
from datetime import datetime
from logging import Logger, getLogger
from pathlib import Path

LOGGER: Logger = getLogger(__package__)


def dump_error(tag: str, exc: BaseException) -> None:
    """Append a traceback to a debug log (temporary debugging aid).

    Tries /config/mymeter_debug.log, falls back to the integration dir, and
    also logs via LOGGER so the failure is visible in `ha core logs` even if
    the file write is blocked.
    """
    msg = "=== %s @ %s ===\n%s\n" % (
        tag,
        datetime.now().isoformat(),
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
    LOGGER.error("MYMETER_DEBUG %s", msg)
    for path in (
        "/config/mymeter_debug.log",
        "/homeassistant/custom_components/mymeter/debug.log",
    ):
        try:
            Path(path).open("a").write(msg)
            return
        except Exception:  # noqa: BLE001
            pass

DOMAIN = "mymeter"
ATTRIBUTION = "Data provided by your MyMeter utility provider."
DEFAULT_SCAN_INTERVAL = 3600

# Config entry keys
CONF_BASE_URL = "base_url"
CONF_METER_ID = "meter_id"
CONF_SESSION_COOKIE = "session_cookie"
CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"

# MyMeter service types (from the Dashboard service-type selector)
SERVICE_TYPE_ELECTRIC = 1
SERVICE_TYPE_WATER = 2
SERVICE_TYPE_NATURAL_GAS = 4
SERVICE_TYPE_BILLING = 23

# MyMeter usage intervals (SelectedInterval on /Usage/Download)
INTERVAL_FIFTEEN_MINUTES = 3
INTERVAL_THIRTY_MINUTES = 4
INTERVAL_HOURLY = 5
INTERVAL_DAILY = 6
INTERVAL_WEEKLY = 8
INTERVAL_MONTHLY = 9

# Endpoint path templates (interpolated with the user-supplied base_url)
URL_DASHBOARD = "{base_url}/Dashboard"
URL_USAGE_DOWNLOAD = "{base_url}/Usage/Download"
URL_CHART_DATA = "{base_url}/Dashboard/ChartData"
URL_ALERTS = "{base_url}/Alerts/Index"

# Sensor keys — must match the dict keys returned by MyMeterDataUpdateCoordinator
SENSOR_MONTH_TO_DATE_KWH = "month_to_date_kwh"
SENSOR_LATEST_INTERVAL_KWH = "latest_interval_kwh"
SENSOR_ACTIVE_ALERTS = "active_alerts"
SENSOR_LAST_READING_TIME = "last_reading_time"
