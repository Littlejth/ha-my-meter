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
    INTERVAL_BILLING,
    INTERVAL_DAILY,
    INTERVAL_HOURLY,
    INTERVAL_WEEKLY,
    LOGGER,
    SENSOR_ACTIVE_ALERTS,
    SENSOR_BILLING_KWH,
    SENSOR_LAST_READING_TIME,
    SENSOR_LATEST_INTERVAL_KWH,
    SENSOR_MONTH_TO_DATE_KWH,
    SENSOR_WEEKLY_KWH,
    SENSOR_HOURLY_KWH,
    SENSOR_NET_KWH,
    SENSOR_ENERGY_MARKERS_COUNT,
    SENSOR_LATEST_MARKER,
    SENSOR_MAX_KWH_TODAY,
    SENSOR_MIN_KWH_TODAY,
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
        year_start = date(today.year, 1, 1)

        # Primary: daily usage (for month-to-date and latest interval)
        # Auth-gated; any auth failure triggers re-login.
        try:
            usage_daily = await client.async_get_usage(
                start=start, end=today, interval=INTERVAL_DAILY
            )
        except MyMeterApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except MyMeterApiClientError as exception:
            raise UpdateFailed(exception) from exception

        # Secondary calls are best-effort: failures don't break the update.
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

        # Hourly (for finer-grained latest interval)
        hourly_usage: list[dict] = []
        try:
            hourly_usage = await client.async_get_usage(
                start=today - timedelta(days=2), end=today, interval=INTERVAL_HOURLY
            )
        except MyMeterApiClientError:
            pass

        # Weekly (chunked for year-to-date)
        weekly_usage: list[dict] = []
        try:
            weekly_usage = await client.async_get_usage_chunked(
                start=year_start, end=today, interval=INTERVAL_WEEKLY
            )
        except MyMeterApiClientError:
            pass

        # Billing period (chunked for year-to-date)
        billing_usage: list[dict] = []
        try:
            billing_usage = await client.async_get_usage_chunked(
                start=year_start, end=today, interval=INTERVAL_BILLING
            )
        except MyMeterApiClientError:
            pass

        # Energy markers
        energy_markers: list[dict] = []
        try:
            energy_markers = await client.async_get_energy_markers()
        except MyMeterApiClientError:
            pass

        # Compute derived values
        month_to_date = 0.0
        if usage_daily:
            month_to_date = sum(
                item["kwh"]
                for item in usage_daily
                if item["start"].year == today.year
                and item["start"].month == today.month
                and item["kwh"] > 0
            )

        latest_daily = usage_daily[-1] if usage_daily else None
        latest_hourly = hourly_usage[-1] if hourly_usage else None

        # Net kWh (Delivered - Received)
        net_kwh = 0.0
        if usage_daily:
            delivered = sum(item["kwh"] for item in usage_daily if item["direction"] == "Delivered")
            received = sum(item["kwh"] for item in usage_daily if item["direction"] == "Received")
            net_kwh = delivered - received

        # Today's max/min from hourly
        max_kwh_today = None
        min_kwh_today = None
        if hourly_usage:
            today_hourly = [
                item for item in hourly_usage
                if item["start"].date() == today and item["direction"] == "Delivered"
            ]
            if today_hourly:
                max_kwh_today = max(item["kwh"] for item in today_hourly)
                min_kwh_today = min(item["kwh"] for item in today_hourly)

        # Latest energy marker
        latest_marker = None
        if energy_markers:
            # Sort by date descending, take first
            sorted_markers = sorted(
                energy_markers,
                key=lambda m: m.get("date", ""),
                reverse=True,
            )
            latest_marker = sorted_markers[0]

        return {
            "usage_daily": usage_daily,
            "usage_hourly": hourly_usage,
            "usage_weekly": weekly_usage,
            "usage_billing": billing_usage,
            "energy_markers": energy_markers,
            SENSOR_MONTH_TO_DATE_KWH: month_to_date,
            SENSOR_LATEST_INTERVAL_KWH: latest_daily["kwh"] if latest_daily else None,
            SENSOR_HOURLY_KWH: latest_hourly["kwh"] if latest_hourly else None,
            SENSOR_WEEKLY_KWH: weekly_usage[-1]["kwh"] if weekly_usage else None,
            SENSOR_BILLING_KWH: billing_usage[-1]["kwh"] if billing_usage else None,
            SENSOR_NET_KWH: net_kwh,
            SENSOR_LAST_READING_TIME: latest_daily["start"] if latest_daily else None,
            "dashboard": dashboard,
            "alerts_html": alerts_html,
            SENSOR_ACTIVE_ALERTS: "alert" in alerts_html.lower(),
            SENSOR_ENERGY_MARKERS_COUNT: len(energy_markers),
            SENSOR_LATEST_MARKER: latest_marker,
            SENSOR_MAX_KWH_TODAY: max_kwh_today,
            SENSOR_MIN_KWH_TODAY: min_kwh_today,
        }