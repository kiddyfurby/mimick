"""Mimick custom integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import MimickCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]

SERVICE_APPLY = "apply"
SERVICE_SET_MANUAL_CONTROL = "set_manual_control"

SERVICE_APPLY_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_ids,
        vol.Optional("force", default=False): cv.boolean,
    }
)

SERVICE_SET_MANUAL_CONTROL_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Required("manual_control"): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Mimick component and register services."""
    hass.data.setdefault(DOMAIN, {})

    async def handle_apply(call: ServiceCall) -> None:
        """Handle mimick.apply service."""
        target_entities = call.data.get("entity_id", [])
        force = call.data.get("force", False)

        for coordinator in hass.data[DOMAIN].values():
            if not isinstance(coordinator, MimickCoordinator):
                continue

            if not target_entities:
                await coordinator.async_adapt_all(force=force)
            else:
                for eid in target_entities:
                    if eid in coordinator.lights:
                        await coordinator.async_adapt_light(eid, force=force)

    async def handle_set_manual_control(call: ServiceCall) -> None:
        """Handle mimick.set_manual_control service."""
        target_entities = call.data.get("entity_id", [])
        manual_state = call.data.get("manual_control", True)

        for coordinator in hass.data[DOMAIN].values():
            if not isinstance(coordinator, MimickCoordinator):
                continue

            for eid in target_entities:
                if eid in coordinator.lights:
                    if manual_state:
                        coordinator._manual_control_brightness[eid] = dt_util.utcnow()
                        coordinator._manual_control_color[eid] = dt_util.utcnow()
                    else:
                        coordinator.clear_manual_control(eid)

    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY,
        handle_apply,
        schema=SERVICE_APPLY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MANUAL_CONTROL,
        handle_set_manual_control,
        schema=SERVICE_SET_MANUAL_CONTROL_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mimick from a config entry."""
    coordinator = MimickCoordinator(
        hass=hass,
        config_entry_id=entry.entry_id,
        data=entry.data,
        options=entry.options,
    )

    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator: MimickCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.update_options(entry.options)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Mimick config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: MimickCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()

    return unload_ok
