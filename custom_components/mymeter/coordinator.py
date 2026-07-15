"""DataUpdateCoordinator for the generic MyMeter integration."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    MyMeterApiClientAuthenticationError,
    MyMeterApiClientError,
)
from .const import (
    CONF_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    SENSOR_ACTIVE_ALERTS,
    SENSOR_LAST_READING_TIME,
    SENSOR_LATEST_INTERVAL_KWH,
    SENSOR_MONTH_TO_DATE_KWH,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import MyMeterConfigEntry

# How far back to pull daily usage so the current month-to-date sum is complete.
USAGE_LOOKBACK_DAYS = 35


class MyMeterDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the MyMeter API."""

    config_entry: MyMeterConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: MyMeterConfigEntry,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=config_entry.options.get(CONF_SCAN_INTERVAL, 3600)
            ),
        )

    async def _async_update_data(self) -> Any:
        """Update data from the MyMeter API."""
        client = self.config_entry.runtime_data.client
        today = date.today()
        start = today - timedelta(days=USAGE_LOOKBACK_DAYS)

        # Usage is the primary, auth-gated call. Any auth failure here must
        # trigger a re-login (ConfigEntryAuthFailed); other errors retry.
        try:
            usage = await client.async_get_usage(
                start=start, end=today, interval=6
            )
        except MyMeterApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except MyMeterApiClientError as exception:
            raise UpdateFailed(exception) from exception

        # Secondary calls are best-effort: a failure here should not break
        # the whole update, but an auth failure still surfaces as None/"".
        dashboard: dict | None = None
        try:
            dashboard = await client.async_get_dashboard()
        except MyMeterApiClientError:
            dashboard = None

        alerts_html = ""
        try:
            alerts_html = await client.async_get_alerts()
        except MyMeterApiClientError:
            alerts_html = ""

        month_to_date = 0.0
        if usage:
            month_to_date = sum(
                item["kwh"]
                for item in usage
                if item["start"].year == today.year
                and item["start"].month == today.month
                and item["kwh"] > 0
            )

        latest = usage[-1] if usage else None

        return {
            "usage": usage,
            SENSOR_MONTH_TO_DATE_KWH: month_to_date,
            SENSOR_LATEST_INTERVAL_KWH: latest["kwh"] if latest else None,
            SENSOR_LAST_READING_TIME: latest["start"] if latest else None,
            "dashboard": dashboard,
            "alerts_html": alerts_html,
            SENSOR_ACTIVE_ALERTS: "alert" in alerts_html.lower(),
        }
