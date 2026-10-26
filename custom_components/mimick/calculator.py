"""Solar calculation and adaptive curve logic for Mimick."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


WEATHER_STATE_CLARITY = {
    "sunny": 1.0,
    "clear-night": 1.0,
    "partlycloudy": 0.75,
    "windy": 0.75,
    "windy-variant": 0.70,
    "cloudy": 0.40,
    "fog": 0.35,
    "rainy": 0.20,
    "pouring": 0.10,
    "lightning": 0.10,
    "lightning-rainy": 0.10,
    "snowy": 0.30,
    "snowy-rainy": 0.20,
    "hail": 0.15,
    "exceptional": 0.50,
}


def calculate_solar_factors(
    elevation: float,
    elevation_min: float = -18.0,
    elevation_max: float = 64.0,
    weather_clarity: float = 1.0,
    weather_influence_pct: int = 0,
) -> tuple[float, float]:
    """Calculate normalized solar factors for (brightness, color_temp).

    Returns:
        (factor_brightness, factor_color)
        - factor_color: Follows the natural outdoor daylight curve based on sun elevation,
          matching real window color temperature (cool natural daylight at noon, warm amber at sunset).
        - factor_brightness: Modulated by weather/clouds during the day so room illuminance
          blends with cloudy vs sunny skies outside, while maintaining the evening floor.
    """
    if elevation_max <= elevation_min:
        base_factor = 1.0 if elevation >= 0 else 0.0
    else:
        # Normalize between 0.0 and 1.0
        x = (elevation - elevation_min) / (elevation_max - elevation_min)
        x = max(0.0, min(1.0, x))
        # Smoothstep interpolation: 3x^2 - 2x^3
        base_factor = x * x * (3.0 - 2.0 * x)

    # Color temperature faithfully tracks the natural outdoor sky spectrum
    factor_color = base_factor

    # Brightness factor is softened during heavy overcast/rainy daytime
    factor_brightness = base_factor
    if weather_influence_pct > 0 and base_factor > 0:
        influence = max(0.0, min(1.0, weather_influence_pct / 100.0))
        clarity = max(0.0, min(1.0, weather_clarity))
        factor_brightness = base_factor * (1.0 - influence * (1.0 - clarity))

    return (max(0.0, min(1.0, factor_brightness)), max(0.0, min(1.0, factor_color)))


def calculate_solar_factor(
    elevation: float,
    elevation_min: float = -18.0,
    elevation_max: float = 64.0,
    weather_clarity: float = 1.0,
    weather_influence_pct: int = 0,
) -> float:
    """Calculate single normalized solar factor for backward compatibility."""
    b_factor, _ = calculate_solar_factors(
        elevation, elevation_min, elevation_max, weather_clarity, weather_influence_pct
    )
    return b_factor


def get_weather_clarity(hass: HomeAssistant, weather_entity: str | None) -> float:
    """Retrieve normalized sky clarity [0.0, 1.0] from a weather or cloud sensor entity.

    1.0 = clear, bright sunny day
    0.0 = dark heavy overcast
    """
    if not weather_entity:
        return 1.0

    state = hass.states.get(weather_entity)
    if not state or state.state in ("unknown", "unavailable"):
        return 1.0

    # 1. Weather domain entity
    if weather_entity.startswith("weather."):
        # Try cloud_coverage attribute (0% - 100%)
        if "cloud_coverage" in state.attributes:
            try:
                cloud_pct = float(state.attributes["cloud_coverage"])
                return max(0.0, min(1.0, 1.0 - (cloud_pct / 100.0)))
            except (ValueError, TypeError):
                pass
        # Fall back to weather condition mapping
        return WEATHER_STATE_CLARITY.get(state.state.lower(), 1.0)

    # 2. Sensor domain entity (e.g. cloud cover %, irradiance W/m², or lux)
    try:
        val = float(state.state)
        unit = state.attributes.get("unit_of_measurement")
        if unit == "%":
            # Cloud cover percentage
            return max(0.0, min(1.0, 1.0 - (val / 100.0)))
        if unit == "W/m²":
            # Solar irradiance: 800+ W/m² is peak clear sun
            return max(0.0, min(1.0, val / 700.0))
        if unit == "lx":
            # Outdoor illuminance: 40,000+ lux is bright daylight
            return max(0.0, min(1.0, val / 30000.0))
    except (ValueError, TypeError):
        pass

    return 1.0


def get_sun_elevation(hass: HomeAssistant) -> float:
    """Retrieve the current sun elevation from Home Assistant's sun entity."""
    sun_state = hass.states.get("sun.sun")
    if sun_state and "elevation" in sun_state.attributes:
        try:
            return float(sun_state.attributes["elevation"])
        except (ValueError, TypeError):
            pass
    return 0.0


def is_sun_rising(hass: HomeAssistant) -> bool:
    """Return True if the sun elevation is rising (between solar midnight and solar noon)."""
    sun_state = hass.states.get("sun.sun")
    if sun_state and "rising" in sun_state.attributes:
        return bool(sun_state.attributes["rising"])
    return False


def calculate_adaptive_values(
    solar_factor: float,
    min_brightness: int,
    max_brightness: int,
    min_kelvin: int,
    max_kelvin: int,
    solar_factor_color: float | None = None,
    is_sleep: bool = False,
    sleep_brightness: int = 10,
    sleep_kelvin: int = 2000,
) -> dict[str, Any]:
    """Calculate target brightness and color temperature based on solar factors or sleep mode."""
    if is_sleep:
        target_brightness = max(1, min(100, sleep_brightness))
        target_kelvin = max(1000, min(10000, sleep_kelvin))
        target_mireds = round(1000000 / target_kelvin)
        return {
            "brightness_pct": target_brightness,
            "brightness_255": round(target_brightness * 255 / 100),
            "kelvin": target_kelvin,
            "mireds": target_mireds,
            "solar_factor": 0.0,
            "solar_factor_color": 0.0,
            "is_sleep": True,
        }

    # Clamp ranges safely
    min_b = max(1, min(100, min_brightness))
    max_b = max(1, min(100, max_brightness))
    min_k = max(1000, min(10000, min_kelvin))
    max_k = max(1000, min(10000, max_kelvin))

    s_color = solar_factor if solar_factor_color is None else solar_factor_color

    target_brightness = round(min_b + solar_factor * (max_b - min_b))
    target_kelvin = round(min_k + s_color * (max_k - min_k))
    target_mireds = round(1000000 / target_kelvin)

    return {
        "brightness_pct": target_brightness,
        "brightness_255": round(target_brightness * 255 / 100),
        "kelvin": target_kelvin,
        "mireds": target_mireds,
        "solar_factor": round(solar_factor, 4),
        "solar_factor_color": round(s_color, 4),
        "is_sleep": False,
    }
