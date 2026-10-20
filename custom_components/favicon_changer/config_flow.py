"""Config flow for favicon integration."""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import (
    CONF_CUSTOM_ICON_PATH,
    CONF_ICON_PRESET,
    CONF_TITLE,
    DOMAIN,
    INTEGRATION_TITLE,
)


class FaviconConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the entry without a form; everything is configured in the sidebar panel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry with nothing applied, so the frontend stays untouched."""
        return self.async_create_entry(
            title=INTEGRATION_TITLE,
            data={CONF_TITLE: "", CONF_ICON_PRESET: "", CONF_CUSTOM_ICON_PATH: ""},
        )
