"""Sensor platform for Mimick."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import MimickCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mimick sensor entities from a config entry."""
    coordinator: MimickCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            MimickBrightnessSensor(coordinator, entry),
            MimickColorTempSensor(coordinator, entry),
            MimickSolarFactorSensor(coordinator, entry),
        ]
    )


class MimickBaseSensor(SensorEntity):
    """Base sensor for Mimick."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        self.coordinator = coordinator
        self.entry = entry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": coordinator.name,
            "manufacturer": "Custom",
            "model": "Mimick Controller",
        }

    async def async_added_to_hass(self) -> None:
        """Register coordinator update listener."""
        self.async_on_remove(self.coordinator.add_listener(self.async_write_ha_state))


class MimickBrightnessSensor(MimickBaseSensor):
    """Sensor showing the current target brightness percentage."""

    _attr_icon = "mdi:brightness-percent"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = "Target Brightness"
        self._attr_unique_id = f"{entry.entry_id}_target_brightness"

    @property
    def native_value(self) -> int | None:
        """Return target brightness percentage for group."""
        if not self.coordinator.lights:
            return None
        # Return values computed for first light (or group defaults)
        val = self.coordinator.get_adaptive_values_for_light(self.coordinator.lights[0])
        return val["brightness_pct"]


class MimickColorTempSensor(MimickBaseSensor):
    """Sensor showing the current target color temperature in Kelvin."""

    _attr_icon = "mdi:thermometer"
    _attr_native_unit_of_measurement = "K"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = "Target Color Temperature"
        self._attr_unique_id = f"{entry.entry_id}_target_color_temp"

    @property
    def native_value(self) -> int | None:
        """Return target Kelvin for group."""
        if not self.coordinator.lights:
            return None
        val = self.coordinator.get_adaptive_values_for_light(self.coordinator.lights[0])
        return val["kelvin"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return mireds attribute."""
        if not self.coordinator.lights:
            return {}
        val = self.coordinator.get_adaptive_values_for_light(self.coordinator.lights[0])
        return {"mireds": val["mireds"]}


class MimickSolarFactorSensor(MimickBaseSensor):
    """Sensor showing the solar progress factor."""

    _attr_icon = "mdi:sun-clock"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry)
        self._attr_name = "Solar Factor"
        self._attr_unique_id = f"{entry.entry_id}_solar_factor"

    @property
    def native_value(self) -> int:
        """Return solar factor percentage."""
        return round(self.coordinator.solar_factor * 100)
