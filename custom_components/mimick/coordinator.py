"""Coordinator managing mimick calculations and light updates."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
    DOMAIN as LIGHT_DOMAIN,
)
from homeassistant.core import Context, Event, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .calculator import (
    calculate_adaptive_values,
    calculate_solar_factors,
    calculate_solar_factor,
    get_sun_elevation,
    get_weather_clarity,
    is_sun_rising,
)
from .const import (
    ATTR_OVERRIDE_ENABLED,
    CONF_ADAPT_BRIGHTNESS,
    CONF_ADAPT_COLOR,
    CONF_INTERVAL,
    CONF_LIGHT_OVERRIDES,
    CONF_LIGHTS,
    CONF_MANUAL_CONTROL_TIMEOUT,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_KELVIN,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_KELVIN,
    CONF_NAME,
    CONF_SLEEP_BRIGHTNESS,
    CONF_SLEEP_ENTITY,
    CONF_SLEEP_KELVIN,
    CONF_SUN_ELEVATION_MAX,
    CONF_SUN_ELEVATION_MIN,
    CONF_TRANSITION,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_INFLUENCE,
    DEFAULT_ADAPT_BRIGHTNESS,
    DEFAULT_ADAPT_COLOR,
    DEFAULT_INTERVAL,
    DEFAULT_MANUAL_CONTROL_TIMEOUT,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_MIN_KELVIN,
    DEFAULT_NAME,
    DEFAULT_SLEEP_BRIGHTNESS,
    DEFAULT_SLEEP_KELVIN,
    DEFAULT_SUN_ELEVATION_MAX,
    DEFAULT_SUN_ELEVATION_MIN,
    DEFAULT_TRANSITION,
    DEFAULT_WEATHER_INFLUENCE,
)

_LOGGER = logging.getLogger(__name__)


class MimickCoordinator:
    """Coordinates sun calculations, light state monitoring, and gentle adaptations."""

    def __init__(self, hass: HomeAssistant, config_entry_id: str, data: dict[str, Any], options: dict[str, Any]) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.config_entry_id = config_entry_id
        self._data = data
        self._options = options

        self._unsub_trackers: list[callback] = []
        self._adaptation_tasks: dict[str, asyncio.Task[None]] = {}
        self._manual_control_brightness: dict[str, datetime] = {}
        self._manual_control_color: dict[str, datetime] = {}
        self._manual_brightness_ahead: dict[str, bool] = {}
        self._manual_color_ahead: dict[str, bool] = {}
        self._our_contexts: set[str] = set()

        # Dynamic switches state
        self._enabled: bool = True
        self._adapt_brightness_enabled: bool = True
        self._adapt_color_enabled: bool = True
        self._sleep_mode: bool = False

        # Target calculation cache
        self._last_solar_factor: float = 0.0
        self._last_elevation: float = 0.0
        self._listeners: list[callback] = []

        self._load_config()

    def _load_config(self) -> None:
        """Load and merge configuration from data and options."""
        cfg = {**self._data, **self._options}

        self.name: str = cfg.get(CONF_NAME, DEFAULT_NAME)
        self.lights: list[str] = cfg.get(CONF_LIGHTS, [])

        self.min_brightness: int = cfg.get(CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS)
        self.max_brightness: int = cfg.get(CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS)
        self.min_kelvin: int = cfg.get(CONF_MIN_KELVIN, DEFAULT_MIN_KELVIN)
        self.max_kelvin: int = cfg.get(CONF_MAX_KELVIN, DEFAULT_MAX_KELVIN)

        self._adapt_brightness_enabled = cfg.get(CONF_ADAPT_BRIGHTNESS, DEFAULT_ADAPT_BRIGHTNESS)
        self._adapt_color_enabled = cfg.get(CONF_ADAPT_COLOR, DEFAULT_ADAPT_COLOR)

        self.transition: float = float(cfg.get(CONF_TRANSITION, DEFAULT_TRANSITION))
        self.interval: int = int(cfg.get(CONF_INTERVAL, DEFAULT_INTERVAL))

        self.sun_elevation_min: float = float(cfg.get(CONF_SUN_ELEVATION_MIN, DEFAULT_SUN_ELEVATION_MIN))
        self.sun_elevation_max: float = float(cfg.get(CONF_SUN_ELEVATION_MAX, DEFAULT_SUN_ELEVATION_MAX))

        self.sleep_entity: str | None = cfg.get(CONF_SLEEP_ENTITY)
        self.sleep_brightness: int = cfg.get(CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS)
        self.sleep_kelvin: int = cfg.get(CONF_SLEEP_KELVIN, DEFAULT_SLEEP_KELVIN)

        self.weather_entity: str | None = cfg.get(CONF_WEATHER_ENTITY)
        self.weather_influence: int = int(cfg.get(CONF_WEATHER_INFLUENCE, DEFAULT_WEATHER_INFLUENCE))

        self.manual_control_timeout: int = cfg.get(CONF_MANUAL_CONTROL_TIMEOUT, DEFAULT_MANUAL_CONTROL_TIMEOUT)
        self.light_overrides: dict[str, dict[str, Any]] = cfg.get(CONF_LIGHT_OVERRIDES, {})

    def update_options(self, options: dict[str, Any]) -> None:
        """Update options and reload settings."""
        self._options = options
        self._load_config()
        self.async_update_listeners()
        if self._enabled:
            self.hass.async_create_task(self.async_adapt_all(force=True))

    def add_listener(self, update_callback: callback) -> callback:
        """Register a callback for coordinator updates."""
        self._listeners.append(update_callback)

        def _remove() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return _remove

    def async_update_listeners(self) -> None:
        """Notify registered entities of state updates."""
        for update_callback in self._listeners:
            update_callback()

    # Property accessors
    @property
    def is_enabled(self) -> bool:
        """Return True if adaptation is globally enabled for this group."""
        return self._enabled

    @property
    def adapt_brightness(self) -> bool:
        """Return True if brightness adaptation is active."""
        return self._adapt_brightness_enabled

    @property
    def adapt_color(self) -> bool:
        """Return True if color adaptation is active."""
        return self._adapt_color_enabled

    @property
    def is_sleep_mode(self) -> bool:
        """Return True if sleep mode is active."""
        if self._sleep_mode:
            return True
        if self.sleep_entity:
            state = self.hass.states.get(self.sleep_entity)
            if state and state.state == "on":
                return True
        return False

    @property
    def solar_factor(self) -> float:
        """Return the current solar factor [0.0 - 1.0]."""
        return self._last_solar_factor

    @property
    def weather_clarity(self) -> float:
        """Return the current sky clarity [0.0 - 1.0]."""
        return getattr(self, "_last_weather_clarity", 1.0)

    @property
    def sun_elevation(self) -> float:
        """Return the current sun elevation."""
        return self._last_elevation

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable adaptation."""
        self._enabled = enabled
        self.async_update_listeners()
        if enabled:
            self.hass.async_create_task(self.async_adapt_all(force=True))

    def set_adapt_brightness(self, enabled: bool) -> None:
        """Enable or disable brightness adaptation."""
        self._adapt_brightness_enabled = enabled
        self.async_update_listeners()

    def set_adapt_color(self, enabled: bool) -> None:
        """Enable or disable color temperature adaptation."""
        self._adapt_color_enabled = enabled
        self.async_update_listeners()

    def set_sleep_mode(self, sleep: bool) -> None:
        """Enable or disable sleep mode."""
        self._sleep_mode = sleep
        self.async_update_listeners()
        self.hass.async_create_task(self.async_adapt_all(force=True))

    def get_light_settings(self, entity_id: str) -> dict[str, Any]:
        """Resolve specific settings for a light, cascading from light overrides to group defaults."""
        override = self.light_overrides.get(entity_id, {})
        has_override = override.get(ATTR_OVERRIDE_ENABLED, False)

        def _val(key: str, default: Any) -> Any:
            if has_override and key in override and override[key] is not None:
                return override[key]
            return default

        return {
            "min_brightness": _val(CONF_MIN_BRIGHTNESS, self.min_brightness),
            "max_brightness": _val(CONF_MAX_BRIGHTNESS, self.max_brightness),
            "min_kelvin": _val(CONF_MIN_KELVIN, self.min_kelvin),
            "max_kelvin": _val(CONF_MAX_KELVIN, self.max_kelvin),
            "adapt_brightness": _val(CONF_ADAPT_BRIGHTNESS, self.adapt_brightness),
            "adapt_color": _val(CONF_ADAPT_COLOR, self.adapt_color),
        }

    def get_adaptive_values_for_light(self, entity_id: str) -> dict[str, Any]:
        """Compute the current target brightness and color temperature for a light."""
        settings = self.get_light_settings(entity_id)
        elevation = get_sun_elevation(self.hass)
        self._last_elevation = elevation
        clarity = get_weather_clarity(self.hass, self.weather_entity)
        self._last_weather_clarity = clarity
        b_factor, c_factor = calculate_solar_factors(
            elevation,
            self.sun_elevation_min,
            self.sun_elevation_max,
            weather_clarity=clarity,
            weather_influence_pct=self.weather_influence,
        )
        self._last_solar_factor = b_factor
        self._last_solar_factor_color = c_factor

        return calculate_adaptive_values(
            solar_factor=b_factor,
            solar_factor_color=c_factor,
            min_brightness=settings["min_brightness"],
            max_brightness=settings["max_brightness"],
            min_kelvin=settings["min_kelvin"],
            max_kelvin=settings["max_kelvin"],
            is_sleep=self.is_sleep_mode,
            sleep_brightness=self.sleep_brightness,
            sleep_kelvin=self.sleep_kelvin,
        )

    def is_manual_controlled(self, entity_id: str, control_type: str = "any") -> bool:
        """Check if a light is currently flagged as manually adjusted for brightness, color, or either."""
        now = dt_util.utcnow()
        timeout = timedelta(minutes=self.manual_control_timeout) if self.manual_control_timeout > 0 else None

        def _is_active(store: dict[str, datetime]) -> bool:
            if entity_id not in store:
                return False
            if timeout and (now - store[entity_id]) > timeout:
                del store[entity_id]
                return False
            return True

        if control_type == "brightness":
            return _is_active(self._manual_control_brightness)
        if control_type == "color":
            return _is_active(self._manual_control_color)
        return _is_active(self._manual_control_brightness) or _is_active(self._manual_control_color)

    def clear_manual_control(self, entity_id: str) -> None:
        """Clear manual control locks for a light."""
        self._manual_control_brightness.pop(entity_id, None)
        self._manual_control_color.pop(entity_id, None)
        self._manual_brightness_ahead.pop(entity_id, None)
        self._manual_color_ahead.pop(entity_id, None)

    async def async_setup(self) -> None:
        """Set up state listeners and background interval updates."""
        if not self.lights:
            _LOGGER.warning("Mimick '%s' has no lights configured", self.name)
            return

        # 1. Track light state changes
        @callback
        def _async_light_state_listener(event: Event) -> None:
            entity_id = event.data.get("entity_id")
            old_state: State | None = event.data.get("old_state")
            new_state: State | None = event.data.get("new_state")

            if not entity_id or not new_state:
                return

            self._handle_light_state_change(entity_id, old_state, new_state, event.context)

        self._unsub_trackers.append(
            async_track_state_change_event(
                self.hass,
                self.lights,
                _async_light_state_listener,
            )
        )

        # 2. Track optional sleep entity if specified
        if self.sleep_entity:
            @callback
            def _async_sleep_entity_changed(event: Event) -> None:
                self.async_update_listeners()
                self.hass.async_create_task(self.async_adapt_all(force=True))

            self._unsub_trackers.append(
                async_track_state_change_event(
                    self.hass,
                    [self.sleep_entity],
                    _async_sleep_entity_changed,
                )
            )

        # 3. Track optional weather / cloud entity if specified
        if self.weather_entity:
            @callback
            def _async_weather_changed(event: Event) -> None:
                self.async_update_listeners()
                self.hass.async_create_task(self.async_adapt_all(force=False))

            self._unsub_trackers.append(
                async_track_state_change_event(
                    self.hass,
                    [self.weather_entity],
                    _async_weather_changed,
                )
            )

        # 4. Schedule periodic adaptation
        @callback
        def _async_interval_tick(now: datetime) -> None:
            if self._enabled:
                self.hass.async_create_task(self.async_adapt_all(force=False))

        self._unsub_trackers.append(
            async_track_time_interval(self.hass, _async_interval_tick, timedelta(seconds=self.interval))
        )

        # Initial check
        self.hass.async_create_task(self.async_adapt_all(force=False))

    def _handle_light_state_change(
        self,
        entity_id: str,
        old_state: State | None,
        new_state: State,
        context: Context,
    ) -> None:
        """Handle turn-on, turn-off, and external manual adjustments."""
        # Clean turn off handling
        if new_state.state == "off":
            # Cancel any running adaptation task immediately
            if task := self._adaptation_tasks.pop(entity_id, None):
                if not task.done():
                    task.cancel()
            # Clear manual control so turning on next time follows adaptive rules
            self.clear_manual_control(entity_id)
            return

        if not self._enabled or new_state.state != "on":
            return

        # Turn ON detection (off -> on)
        just_turned_on = old_state is None or old_state.state != "on"
        if just_turned_on:
            self.clear_manual_control(entity_id)
            # Adapt immediately upon turn on
            self.hass.async_create_task(self.async_adapt_light(entity_id, is_turn_on=True))
            return

        # While on: check if this was our own call
        if context.id in self._our_contexts:
            return

        # If brightness or color temp changed externally while already ON, track manual control
        if old_state and old_state.state == "on":
            old_b = old_state.attributes.get(ATTR_BRIGHTNESS)
            new_b = new_state.attributes.get(ATTR_BRIGHTNESS)
            old_ct = old_state.attributes.get(ATTR_COLOR_TEMP_KELVIN)
            new_ct = new_state.attributes.get(ATTR_COLOR_TEMP_KELVIN)

            settings = self.get_light_settings(entity_id)
            b_changed = settings["adapt_brightness"] and old_b != new_b and abs((old_b or 0) - (new_b or 0)) > 5
            ct_changed = settings["adapt_color"] and old_ct != new_ct and abs((old_ct or 0) - (new_ct or 0)) > 40

            if b_changed and new_b is not None:
                sun_rising = is_sun_rising(self.hass)
                values = self.get_adaptive_values_for_light(entity_id)
                target_b = values["brightness_255"]
                is_ahead = (not sun_rising and new_b < target_b) or (sun_rising and new_b > target_b)
                self._manual_control_brightness[entity_id] = dt_util.utcnow()
                self._manual_brightness_ahead[entity_id] = is_ahead
                _LOGGER.debug(
                    "Mimick '%s': light '%s' brightness set to %s (target=%s, rising=%s, is_ahead=%s)",
                    self.name,
                    entity_id,
                    new_b,
                    target_b,
                    sun_rising,
                    is_ahead,
                )

            if ct_changed and new_ct is not None:
                sun_rising = is_sun_rising(self.hass)
                values = self.get_adaptive_values_for_light(entity_id)
                target_ct = values["kelvin"]
                is_ahead = (not sun_rising and new_ct < target_ct) or (sun_rising and new_ct > target_ct)
                self._manual_control_color[entity_id] = dt_util.utcnow()
                self._manual_color_ahead[entity_id] = is_ahead
                _LOGGER.debug(
                    "Mimick '%s': light '%s' color set to %sK (target=%sK, rising=%s, is_ahead=%s)",
                    self.name,
                    entity_id,
                    new_ct,
                    target_ct,
                    sun_rising,
                    is_ahead,
                )

    async def async_adapt_light(
        self,
        entity_id: str,
        is_turn_on: bool = False,
        force: bool = False,
    ) -> None:
        """Adapt a single light if needed, respecting Lightener, manual overrides, and ratchet freewheeling."""
        if not self._enabled:
            return

        state = self.hass.states.get(entity_id)
        if not state or state.state != "on":
            return

        settings = self.get_light_settings(entity_id)
        adapt_b = settings["adapt_brightness"] and self._adapt_brightness_enabled
        adapt_c = settings["adapt_color"] and self._adapt_color_enabled

        if not adapt_b and not adapt_c:
            return

        values = self.get_adaptive_values_for_light(entity_id)
        target_brightness = values["brightness_255"]
        target_kelvin = values["kelvin"]

        sun_rising = is_sun_rising(self.hass)
        user_b = state.attributes.get(ATTR_BRIGHTNESS)
        user_ct = state.attributes.get(ATTR_COLOR_TEMP_KELVIN)

        # Catch-Up Resume (Directional Ratchet) for Brightness
        if self.is_manual_controlled(entity_id, "brightness") and user_b is not None:
            is_ahead = self._manual_brightness_ahead.get(entity_id, False)
            if is_ahead:
                # In falling phase (afternoon/evening), once target falls to or below user_b, re-engage!
                if not sun_rising and target_brightness <= user_b:
                    _LOGGER.info(
                        "Mimick '%s': Ratchet re-engaged for '%s' brightness (target %s <= user %s)",
                        self.name,
                        entity_id,
                        target_brightness,
                        user_b,
                    )
                    self._manual_control_brightness.pop(entity_id, None)
                    self._manual_brightness_ahead.pop(entity_id, None)
                # In rising phase (morning), once target rises to or above user_b, re-engage!
                elif sun_rising and target_brightness >= user_b:
                    _LOGGER.info(
                        "Mimick '%s': Ratchet re-engaged for '%s' brightness (target %s >= user %s)",
                        self.name,
                        entity_id,
                        target_brightness,
                        user_b,
                    )
                    self._manual_control_brightness.pop(entity_id, None)
                    self._manual_brightness_ahead.pop(entity_id, None)

        # Catch-Up Resume (Directional Ratchet) for Color Temperature
        if self.is_manual_controlled(entity_id, "color") and user_ct is not None:
            is_ahead = self._manual_color_ahead.get(entity_id, False)
            if is_ahead:
                if not sun_rising and target_kelvin <= user_ct:
                    _LOGGER.info(
                        "Mimick '%s': Ratchet re-engaged for '%s' color (target %sK <= user %sK)",
                        self.name,
                        entity_id,
                        target_kelvin,
                        user_ct,
                    )
                    self._manual_control_color.pop(entity_id, None)
                    self._manual_color_ahead.pop(entity_id, None)
                elif sun_rising and target_kelvin >= user_ct:
                    _LOGGER.info(
                        "Mimick '%s': Ratchet re-engaged for '%s' color (target %sK >= user %sK)",
                        self.name,
                        entity_id,
                        target_kelvin,
                        user_ct,
                    )
                    self._manual_control_color.pop(entity_id, None)
                    self._manual_color_ahead.pop(entity_id, None)

        adapt_color_allowed = adapt_c and (force or is_turn_on or not self.is_manual_controlled(entity_id, "color"))
        adapt_brightness_allowed = adapt_b and (force or is_turn_on or not self.is_manual_controlled(entity_id, "brightness"))

        if not adapt_color_allowed and not adapt_brightness_allowed:
            return

        service_data: dict[str, Any] = {"entity_id": entity_id}
        needs_update = False

        # 1. Color adaptation
        if adapt_color_allowed:
            current_kelvin = state.attributes.get(ATTR_COLOR_TEMP_KELVIN)
            if current_kelvin is None or abs(current_kelvin - target_kelvin) > 35 or force:
                service_data[ATTR_COLOR_TEMP_KELVIN] = target_kelvin
                needs_update = True

        # 2. Brightness adaptation
        if adapt_brightness_allowed:
            current_brightness = state.attributes.get(ATTR_BRIGHTNESS)
            if current_brightness is None or abs(current_brightness - target_brightness) > 8 or force:
                service_data[ATTR_BRIGHTNESS] = target_brightness
                needs_update = True

        if not needs_update:
            return

        # Set transition: short 0.5s for turn-on (clean and flash-free), or gentle group transition for periodic
        if is_turn_on:
            service_data[ATTR_TRANSITION] = 0.5
        else:
            service_data[ATTR_TRANSITION] = self.transition

        call_context = Context()
        self._our_contexts.add(call_context.id)
        # Keep context set small
        if len(self._our_contexts) > 100:
            self._our_contexts.pop()

        try:
            await self.hass.services.async_call(
                LIGHT_DOMAIN,
                "turn_on",
                service_data,
                context=call_context,
                blocking=False,
            )
        except Exception as err:
            _LOGGER.error("Failed to adapt light '%s': %s", entity_id, err)

    async def async_adapt_all(self, force: bool = False) -> None:
        """Adapt all active lights in the group."""
        if not self._enabled:
            return

        for entity_id in self.lights:
            state = self.hass.states.get(entity_id)
            if state and state.state == "on":
                # Cancel existing in-flight task for this light if any
                if old_task := self._adaptation_tasks.get(entity_id):
                    if not old_task.done():
                        old_task.cancel()

                task = self.hass.async_create_task(
                    self.async_adapt_light(entity_id, is_turn_on=False, force=force)
                )
                self._adaptation_tasks[entity_id] = task

        self.async_update_listeners()

    async def async_unload(self) -> None:
        """Unload and clean up listeners and tasks."""
        for unsub in self._unsub_trackers:
            unsub()
        self._unsub_trackers.clear()

        for task in self._adaptation_tasks.values():
            if not task.done():
                task.cancel()
        self._adaptation_tasks.clear()
        self._listeners.clear()
