"""Sensor platform for mymeter."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy

from .entity import MyMeterEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MyMeterDataUpdateCoordinator
    from .data import MyMeterConfigEntry

ENTITY_DESCRIPTIONS = (
    SensorEntityDescription(
        key="month_to_date_kwh",
        name="Month to Date Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="latest_interval_kwh",
        name="Latest Interval Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key="active_alerts",
        name="Active Alerts",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="last_reading_time",
        name="Last Reading Time",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: MyMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    async_add_entities(
        MyMeterSensor(
            coordinator=entry.runtime_data.coordinator,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
    )


class MyMeterSensor(MyMeterEntity, SensorEntity):
    """mymeter Sensor class."""

    def __init__(
        self,
        coordinator: MyMeterDataUpdateCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        )

    @property
    def native_value(self) -> int | float | datetime | None:
        """Return the native value of the sensor."""
        data = self.coordinator.data
        key = self.entity_description.key
        if key == "latest_interval_kwh":
            return data.get("latest_kwh")
        if key == "last_reading_time":
            return data.get("latest_start")
        if key == "active_alerts":
            return 1 if data.get("alerts_active") else 0
        return data.get(key)
