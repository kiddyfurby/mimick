"""Config flow and Options flow for Mimick."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    ATTR_OVERRIDE_ENABLED,
    ATTR_SELECTED_LIGHT,
    CONF_ADAPT_BRIGHTNESS,
    CONF_ADAPT_COLOR,
    CONF_DEBUG_LOGGING,
    CONF_INTERVAL,
    CONF_LIGHT_OVERRIDES,
    CONF_LIGHTS,
    CONF_MAX_BRIGHTNESS,
    CONF_MAX_KELVIN,
    CONF_MIN_BRIGHTNESS,
    CONF_MIN_KELVIN,
    CONF_NAME,
    CONF_SLEEP_BRIGHTNESS,
    CONF_SLEEP_ENTITY,
    CONF_SLEEP_KELVIN,
    CONF_TRANSITION,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_INFLUENCE,
    DEFAULT_ADAPT_BRIGHTNESS,
    DEFAULT_ADAPT_COLOR,
    DEFAULT_DEBUG_LOGGING,
    DEFAULT_INTERVAL,
    DEFAULT_MAX_BRIGHTNESS,
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_BRIGHTNESS,
    DEFAULT_MIN_KELVIN,
    DEFAULT_NAME,
    DEFAULT_SLEEP_BRIGHTNESS,
    DEFAULT_SLEEP_KELVIN,
    DEFAULT_TRANSITION,
    DEFAULT_WEATHER_INFLUENCE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class MimickConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mimick."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial group creation step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_LIGHTS):
                errors[CONF_LIGHTS] = "no_lights_selected"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
                vol.Required(CONF_LIGHTS, default=[]): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="light", multiple=True)
                ),
                vol.Required(CONF_MIN_BRIGHTNESS, default=DEFAULT_MIN_BRIGHTNESS): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Required(CONF_MAX_BRIGHTNESS, default=DEFAULT_MAX_BRIGHTNESS): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Required(CONF_MIN_KELVIN, default=DEFAULT_MIN_KELVIN): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1800, max=6500, step=50, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="K")
                ),
                vol.Required(CONF_MAX_KELVIN, default=DEFAULT_MAX_KELVIN): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1800, max=6500, step=50, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="K")
                ),
                vol.Required(CONF_ADAPT_BRIGHTNESS, default=DEFAULT_ADAPT_BRIGHTNESS): selector.BooleanSelector(),
                vol.Required(CONF_ADAPT_COLOR, default=DEFAULT_ADAPT_COLOR): selector.BooleanSelector(),
                vol.Required(CONF_TRANSITION, default=DEFAULT_TRANSITION): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.0, max=300.0, step=1.0, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")
                ),
                vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=10, max=600, step=5, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")
                ),
                vol.Optional(CONF_SLEEP_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["input_boolean", "switch", "binary_sensor"])
                ),
                vol.Optional(CONF_SLEEP_BRIGHTNESS, default=DEFAULT_SLEEP_BRIGHTNESS): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Optional(CONF_SLEEP_KELVIN, default=DEFAULT_SLEEP_KELVIN): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1800, max=6500, step=50, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="K")
                ),
                vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["weather", "sensor"])
                ),
                vol.Optional(CONF_WEATHER_INFLUENCE, default=DEFAULT_WEATHER_INFLUENCE): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=100, step=5, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Optional(CONF_DEBUG_LOGGING, default=DEFAULT_DEBUG_LOGGING): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow for this entry."""
        return MimickOptionsFlowHandler(config_entry)


class MimickOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Mimick with group and light-level customization."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        self._options: dict[str, Any] = {}
        self._selected_light: str | None = None

    def _get_current(self, key: str, default: Any) -> Any:
        """Get the current configuration value from options or fallback to entry data."""
        if self._options and key in self._options:
            return self._options[key]
        return self.config_entry.options.get(key, self.config_entry.data.get(key, default))

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show the options menu to choose between group settings and light overrides."""
        if not self._options:
            self._options = dict(self.config_entry.options)
        return self.async_show_menu(
            step_id="init",
            menu_options=["group_settings", "light_overrides"],
        )

    async def async_step_group_settings(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Edit group-wide default settings."""
        if not self._options:
            self._options = dict(self.config_entry.options)

        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        configured_lights = self._get_current(CONF_LIGHTS, [])

        schema = vol.Schema(
            {
                vol.Required(CONF_LIGHTS, default=configured_lights): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="light", multiple=True)
                ),
                vol.Required(
                    CONF_MIN_BRIGHTNESS,
                    default=self._get_current(CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Required(
                    CONF_MAX_BRIGHTNESS,
                    default=self._get_current(CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Required(
                    CONF_MIN_KELVIN,
                    default=self._get_current(CONF_MIN_KELVIN, DEFAULT_MIN_KELVIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1800, max=6500, step=50, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="K")
                ),
                vol.Required(
                    CONF_MAX_KELVIN,
                    default=self._get_current(CONF_MAX_KELVIN, DEFAULT_MAX_KELVIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1800, max=6500, step=50, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="K")
                ),
                vol.Required(
                    CONF_ADAPT_BRIGHTNESS,
                    default=self._get_current(CONF_ADAPT_BRIGHTNESS, DEFAULT_ADAPT_BRIGHTNESS),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_ADAPT_COLOR,
                    default=self._get_current(CONF_ADAPT_COLOR, DEFAULT_ADAPT_COLOR),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_TRANSITION,
                    default=self._get_current(CONF_TRANSITION, DEFAULT_TRANSITION),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.0, max=300.0, step=1.0, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")
                ),
                vol.Required(
                    CONF_INTERVAL,
                    default=self._get_current(CONF_INTERVAL, DEFAULT_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=10, max=600, step=5, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="s")
                ),
                vol.Optional(
                    CONF_SLEEP_ENTITY,
                    description={"suggested_value": self._get_current(CONF_SLEEP_ENTITY, None)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["input_boolean", "switch", "binary_sensor"])
                ),
                vol.Optional(
                    CONF_SLEEP_BRIGHTNESS,
                    default=self._get_current(CONF_SLEEP_BRIGHTNESS, DEFAULT_SLEEP_BRIGHTNESS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Optional(
                    CONF_SLEEP_KELVIN,
                    default=self._get_current(CONF_SLEEP_KELVIN, DEFAULT_SLEEP_KELVIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1800, max=6500, step=50, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="K")
                ),
                vol.Optional(
                    CONF_WEATHER_ENTITY,
                    description={"suggested_value": self._get_current(CONF_WEATHER_ENTITY, None)},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["weather", "sensor"])
                ),
                vol.Optional(
                    CONF_WEATHER_INFLUENCE,
                    default=self._get_current(CONF_WEATHER_INFLUENCE, DEFAULT_WEATHER_INFLUENCE),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=100, step=5, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Optional(
                    CONF_DEBUG_LOGGING,
                    default=self._get_current(CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING),
                ): selector.BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="group_settings", data_schema=schema)

    async def async_step_light_overrides(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1 of overrides: choose a light from the group to customize."""
        if not self._options:
            self._options = dict(self.config_entry.options)

        configured_lights = self._get_current(CONF_LIGHTS, [])
        if not configured_lights:
            return self.async_abort(reason="no_lights")

        if user_input is not None and ATTR_SELECTED_LIGHT in user_input:
            self._selected_light = user_input[ATTR_SELECTED_LIGHT]
            return await self.async_step_light_override_edit()

        options = [{"value": eid, "label": eid} for eid in configured_lights]
        schema = vol.Schema(
            {
                vol.Required(ATTR_SELECTED_LIGHT, default=configured_lights[0]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
            }
        )

        return self.async_show_form(step_id="light_overrides", data_schema=schema)

    async def async_step_light_override_edit(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2 of overrides: edit min/max brightness, kelvin, and adaptation flags for selected light."""
        if not self._selected_light:
            return await self.async_step_light_overrides()

        overrides = self._options.setdefault(CONF_LIGHT_OVERRIDES, {})
        current_override = overrides.get(self._selected_light, {})

        if user_input is not None:
            overrides[self._selected_light] = user_input
            self._options[CONF_LIGHT_OVERRIDES] = overrides
            return self.async_create_entry(title="", data=self._options)

        group_min_b = self._get_current(CONF_MIN_BRIGHTNESS, DEFAULT_MIN_BRIGHTNESS)
        group_max_b = self._get_current(CONF_MAX_BRIGHTNESS, DEFAULT_MAX_BRIGHTNESS)
        group_min_k = self._get_current(CONF_MIN_KELVIN, DEFAULT_MIN_KELVIN)
        group_max_k = self._get_current(CONF_MAX_KELVIN, DEFAULT_MAX_KELVIN)
        group_adapt_b = self._get_current(CONF_ADAPT_BRIGHTNESS, DEFAULT_ADAPT_BRIGHTNESS)
        group_adapt_c = self._get_current(CONF_ADAPT_COLOR, DEFAULT_ADAPT_COLOR)

        schema = vol.Schema(
            {
                vol.Required(
                    ATTR_OVERRIDE_ENABLED,
                    default=current_override.get(ATTR_OVERRIDE_ENABLED, False),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_ADAPT_BRIGHTNESS,
                    default=current_override.get(CONF_ADAPT_BRIGHTNESS, group_adapt_b),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_ADAPT_COLOR,
                    default=current_override.get(CONF_ADAPT_COLOR, group_adapt_c),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_MIN_BRIGHTNESS,
                    default=current_override.get(CONF_MIN_BRIGHTNESS, group_min_b),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Required(
                    CONF_MAX_BRIGHTNESS,
                    default=current_override.get(CONF_MAX_BRIGHTNESS, group_max_b),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="%")
                ),
                vol.Required(
                    CONF_MIN_KELVIN,
                    default=current_override.get(CONF_MIN_KELVIN, group_min_k),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1800, max=6500, step=50, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="K")
                ),
                vol.Required(
                    CONF_MAX_KELVIN,
                    default=current_override.get(CONF_MAX_KELVIN, group_max_k),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1800, max=6500, step=50, mode=selector.NumberSelectorMode.SLIDER, unit_of_measurement="K")
                ),
            }
        )

        return self.async_show_form(
            step_id="light_override_edit",
            data_schema=schema,
            description_placeholders={"light_id": self._selected_light},
        )
