"""Constants for Mimick."""

from __future__ import annotations

DOMAIN = "mimick"

# Configuration keys
CONF_NAME = "name"
CONF_LIGHTS = "lights"

CONF_MIN_BRIGHTNESS = "min_brightness"
CONF_MAX_BRIGHTNESS = "max_brightness"
CONF_MIN_KELVIN = "min_kelvin"
CONF_MAX_KELVIN = "max_kelvin"

CONF_ADAPT_BRIGHTNESS = "adapt_brightness"
CONF_ADAPT_COLOR = "adapt_color"

CONF_TRANSITION = "transition"
CONF_INTERVAL = "interval"

CONF_SUN_ELEVATION_MIN = "sun_elevation_min"
CONF_SUN_ELEVATION_MAX = "sun_elevation_max"

CONF_SLEEP_ENTITY = "sleep_entity"
CONF_SLEEP_BRIGHTNESS = "sleep_brightness"
CONF_SLEEP_KELVIN = "sleep_kelvin"

CONF_WEATHER_ENTITY = "weather_entity"
CONF_WEATHER_INFLUENCE = "weather_influence"

CONF_MANUAL_CONTROL_TIMEOUT = "manual_control_timeout"
CONF_LIGHT_OVERRIDES = "light_overrides"

# Light override sub-keys
ATTR_OVERRIDE_ENABLED = "override_enabled"
ATTR_SELECTED_LIGHT = "selected_light"

# Default values
DEFAULT_NAME = "Mimick"
DEFAULT_MIN_BRIGHTNESS = 30
DEFAULT_MAX_BRIGHTNESS = 100
DEFAULT_MIN_KELVIN = 2200
DEFAULT_MAX_KELVIN = 5500  # Natural outdoor daylight peak
DEFAULT_ADAPT_BRIGHTNESS = True
DEFAULT_ADAPT_COLOR = True
DEFAULT_TRANSITION = 2.0  # Safe short transition (avoiding hardware timer locking)
DEFAULT_INTERVAL = 90  # Seconds between periodic checks
DEFAULT_WEATHER_INFLUENCE = 30  # Percentage (0-100%) modulation during daytime
DEFAULT_SUN_ELEVATION_MIN = -18.0  # Astronomical twilight
DEFAULT_SUN_ELEVATION_MAX = 64.0  # Approximate peak solar elevation
DEFAULT_SLEEP_BRIGHTNESS = 10
DEFAULT_SLEEP_KELVIN = 2000
DEFAULT_MANUAL_CONTROL_TIMEOUT = 60  # Minutes (0 = until light turns off and on)

# Service and attribute constants
ATTR_FACTOR = "solar_factor"
ATTR_TARGET_BRIGHTNESS = "target_brightness"
ATTR_TARGET_KELVIN = "target_kelvin"
ATTR_TARGET_MIREDS = "target_mireds"
ATTR_MANUAL_CONTROL = "manual_control"
