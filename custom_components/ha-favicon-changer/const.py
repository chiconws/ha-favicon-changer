"""Constants and shared helpers for the favicon integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

DOMAIN = "ha-favicon-changer"
INTEGRATION_TITLE = "Favicon Changer"

CONF_TITLE = "title"
CONF_ICON_PRESET = "icon_preset"
CONF_CUSTOM_ICON_PATH = "custom_icon_path"

PRESET_PUBLIC_ROOT = "/api/ha-favicon-changer/presets"

CUSTOM_ICON_PUBLIC_ROOT = "/api/ha-favicon-changer/custom"
CUSTOM_ICON_STORAGE_ROOT = ("www", "favicon-changer-custom")
CUSTOM_ICON_SLOT = "current"
MAX_UPLOAD_BYTES = 1024 * 1024
MAX_TITLE_LENGTH = 120


def clean_string(value: Any) -> str | None:
    """Return a stripped string, or None for blanks and non-strings."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def entry_values(config_entry: ConfigEntry | None) -> dict[str, Any]:
    """Return config entry data merged with its options."""
    if config_entry is None:
        return {}
    return {**config_entry.data, **config_entry.options}
