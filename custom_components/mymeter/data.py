"""Custom types for the mymeter integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.loader import Integration

from .api import MyMeterApiClient
from .coordinator import MyMeterDataUpdateCoordinator


@dataclass
class MyMeterData:
    """Data for the MyMeter integration."""

    client: MyMeterApiClient
    coordinator: MyMeterDataUpdateCoordinator
    integration: Integration


type MyMeterConfigEntry = ConfigEntry[MyMeterData]
