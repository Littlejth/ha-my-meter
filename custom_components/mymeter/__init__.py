"""The mymeter integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import MyMeterApiClient
from .const import (
    CONF_BASE_URL,
    CONF_METER_ID,
    CONF_SESSION_COOKIE,
    CONF_TOKEN,
)
from .coordinator import MyMeterDataUpdateCoordinator
from .data import MyMeterData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import MyMeterConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR]


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyMeterConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    try:
        client = MyMeterApiClient(
            base_url=entry.data[CONF_BASE_URL],
            meter_id=entry.data[CONF_METER_ID],
            session_cookie=entry.data[CONF_SESSION_COOKIE],
            token=entry.data[CONF_TOKEN],
            session=async_get_clientsession(hass),
        )
        coordinator = MyMeterDataUpdateCoordinator(hass=hass, config_entry=entry)
        entry.runtime_data = MyMeterData(
            client=client,
            coordinator=coordinator,
            integration=async_get_loaded_integration(hass, entry.domain),
        )

        # https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
        await coordinator.async_config_entry_first_refresh()

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    except Exception as exc:  # pylint: disable=broad-except
        from .const import dump_error

        dump_error("async_setup_entry", exc)
        raise
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: MyMeterConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant,
    entry: MyMeterConfigEntry,
) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
