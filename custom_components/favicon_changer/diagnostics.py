"""Diagnostics: the active title and icon source."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import entry_values
from .custom_icons import get_custom_icon_preview_url


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return the configuration and the custom icon in use, if any."""
    return {
        "config": entry_values(entry),
        "custom_icon": await hass.async_add_executor_job(get_custom_icon_preview_url, hass),
    }
