"""Config flow for favicon integration."""

from __future__ import annotations

import logging
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
from .preset_catalog import load_preset_catalog

_LOGGER = logging.getLogger(__name__)


class FaviconConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the entry without a form; everything is configured in the sidebar panel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry with nothing applied, so the frontend stays untouched."""
        if not await self.hass.async_add_executor_job(load_preset_catalog):
            _LOGGER.error("Config flow aborted: no valid shipped presets available")
            return self.async_abort(reason="no_presets_available")

        return self.async_create_entry(
            title=INTEGRATION_TITLE,
            data={CONF_TITLE: "", CONF_ICON_PRESET: "", CONF_CUSTOM_ICON_PATH: ""},
        )
