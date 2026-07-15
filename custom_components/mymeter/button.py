"""Button platform for mymeter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import MyMeterEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MyMeterDataUpdateCoordinator
    from .data import MyMeterConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: MyMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    async_add_entities(
        [MyMeterRefreshButton(coordinator=entry.runtime_data.coordinator)]
    )


class MyMeterRefreshButton(MyMeterEntity, ButtonEntity):
    """Button to force an immediate refresh of the MyMeter data."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: MyMeterDataUpdateCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_refresh"

    async def async_press(self) -> None:
        """Force a refresh of the MyMeter coordinator."""
        await self.coordinator.async_request_refresh()
