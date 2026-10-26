"""Switch platform for Mimick."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    ATTR_FACTOR,
    ATTR_MANUAL_CONTROL,
    CONF_LIGHTS,
    DOMAIN,
)
from .coordinator import MimickCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Mimick switch entities from a config entry."""
    coordinator: MimickCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            MimickMasterSwitch(coordinator, entry),
            MimickAdaptBrightnessSwitch(coordinator, entry),
            MimickAdaptColorSwitch(coordinator, entry),
            MimickSleepSwitch(coordinator, entry),
        ]
    )


class MimickBaseSwitch(SwitchEntity):
    """Base switch entity for Mimick."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize base switch."""
        self.coordinator = coordinator
        self.entry = entry
        self._slug = slugify(coordinator.name)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": coordinator.name,
            "manufacturer": "Custom",
            "model": "Mimick Controller",
        }

    async def async_added_to_hass(self) -> None:
        """Register coordinator update listener."""
        self.async_on_remove(self.coordinator.add_listener(self.async_write_ha_state))


class MimickMasterSwitch(MimickBaseSwitch):
    """Main master switch enabling or disabling adaptation for the group."""

    _attr_icon = "theme-mode"

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize master switch."""
        super().__init__(coordinator, entry)
        self._attr_name = "Mimicking"
        self._attr_unique_id = f"{entry.entry_id}_master"

    @property
    def is_on(self) -> bool:
        """Return True if adaptation is globally enabled for this group."""
        return self.coordinator.is_enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic state attributes."""
        manual_lights = [eid for eid in self.coordinator.lights if self.coordinator.is_manual_controlled(eid)]
        return {
            CONF_LIGHTS: self.coordinator.lights,
            ATTR_FACTOR: self.coordinator.solar_factor,
            "sun_elevation": self.coordinator.sun_elevation,
            "weather_clarity": self.coordinator.weather_clarity,
            "weather_entity": self.coordinator.weather_entity,
            ATTR_MANUAL_CONTROL: manual_lights,
            "sleep_mode": self.coordinator.is_sleep_mode,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on adaptation."""
        self.coordinator.set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off adaptation."""
        self.coordinator.set_enabled(False)


class MimickAdaptBrightnessSwitch(MimickBaseSwitch):
    """Switch to toggle brightness adaptation."""

    _attr_icon = "mdi:brightness-6"

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize brightness switch."""
        super().__init__(coordinator, entry)
        self._attr_name = "Adapt Brightness"
        self._attr_unique_id = f"{entry.entry_id}_adapt_brightness"

    @property
    def is_on(self) -> bool:
        """Return True if brightness adaptation is active."""
        return self.coordinator.adapt_brightness

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on brightness adaptation."""
        self.coordinator.set_adapt_brightness(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off brightness adaptation."""
        self.coordinator.set_adapt_brightness(False)


class MimickAdaptColorSwitch(MimickBaseSwitch):
    """Switch to toggle color temperature adaptation."""

    _attr_icon = "mdi:palette-outline"

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize color switch."""
        super().__init__(coordinator, entry)
        self._attr_name = "Adapt Color"
        self._attr_unique_id = f"{entry.entry_id}_adapt_color"

    @property
    def is_on(self) -> bool:
        """Return True if color temperature adaptation is active."""
        return self.coordinator.adapt_color

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on color adaptation."""
        self.coordinator.set_adapt_color(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off color adaptation."""
        self.coordinator.set_adapt_color(False)


class MimickSleepSwitch(MimickBaseSwitch):
    """Switch to toggle sleep mode manually."""

    _attr_icon = "mdi:weather-night"

    def __init__(self, coordinator: MimickCoordinator, entry: ConfigEntry) -> None:
        """Initialize sleep switch."""
        super().__init__(coordinator, entry)
        self._attr_name = "Sleep Mode"
        self._attr_unique_id = f"{entry.entry_id}_sleep_mode"

    @property
    def is_on(self) -> bool:
        """Return True if sleep mode is currently on."""
        return self.coordinator.is_sleep_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on sleep mode."""
        self.coordinator.set_sleep_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off sleep mode."""
        self.coordinator.set_sleep_mode(False)
