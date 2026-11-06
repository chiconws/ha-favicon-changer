"""Diagnostics: the active title and icon source."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CUSTOM_ICON_PATH, clean_string, entry_values
from .custom_icons import get_custom_icon_preview_url


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the configuration and the custom icon in use, if any."""
    config = entry_values(entry)
    custom_icon = None
    # An upload stays on disk after switching back to a preset; report it only when active.
    if clean_string(config.get(CONF_CUSTOM_ICON_PATH)):
        custom_icon = await hass.async_add_executor_job(
            get_custom_icon_preview_url, hass
        )
    return {"config": config, "custom_icon": custom_icon}
