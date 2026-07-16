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

from .const import (
    SENSOR_ACTIVE_ALERTS,
    SENSOR_BILLING_KWH,
    SENSOR_ENERGY_MARKERS_COUNT,
    SENSOR_HOURLY_KWH,
    SENSOR_LAST_READING_TIME,
    SENSOR_LATEST_INTERVAL_KWH,
    SENSOR_LATEST_MARKER,
    SENSOR_MAX_KWH_TODAY,
    SENSOR_MIN_KWH_TODAY,
    SENSOR_MONTH_TO_DATE_KWH,
    SENSOR_NET_KWH,
    SENSOR_WEEKLY_KWH,
)
from .entity import MyMeterEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MyMeterDataUpdateCoordinator
    from .data import MyMeterConfigEntry

ENTITY_DESCRIPTIONS = (
    SensorEntityDescription(
        key=SENSOR_MONTH_TO_DATE_KWH,
        name="Month to Date Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key=SENSOR_LATEST_INTERVAL_KWH,
        name="Latest Interval Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key=SENSOR_HOURLY_KWH,
        name="Latest Hourly Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key=SENSOR_WEEKLY_KWH,
        name="Latest Weekly Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key=SENSOR_BILLING_KWH,
        name="Latest Billing Period Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key=SENSOR_NET_KWH,
        name="Net Usage (Delivered - Received)",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SensorEntityDescription(
        key=SENSOR_MAX_KWH_TODAY,
        name="Max Hourly Usage Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=SENSOR_MIN_KWH_TODAY,
        name="Min Hourly Usage Today",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=SENSOR_ACTIVE_ALERTS,
        name="Active Alerts",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=SENSOR_ENERGY_MARKERS_COUNT,
        name="Energy Markers Count",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=SENSOR_LATEST_MARKER,
        name="Latest Energy Marker",
    ),
    SensorEntityDescription(
        key=SENSOR_LAST_READING_TIME,
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
    def native_value(self) -> int | float | datetime | str | dict | None:
        """Return the native value of the sensor."""
        value = self.coordinator.data.get(self.entity_description.key)
        # For the latest marker dict, return a summary string
        if isinstance(value, dict):
            return f"{value.get('title', 'Marker')} - {value.get('date', 'Unknown date')}"
        return value

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return additional attributes for the sensor."""
        if self.entity_description.key == SENSOR_LATEST_MARKER:
            marker = self.coordinator.data.get(SENSOR_LATEST_MARKER)
            if isinstance(marker, dict):
                return {
                    "title": marker.get("title", ""),
                    "date": marker.get("date", ""),
                    "description": marker.get("description", ""),
                    "type": marker.get("type", "unknown"),
                    "marker_id": marker.get("id", ""),
                }
        return None