"""Config flow for favicon integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CUSTOM_ICON_PATH,
    CONF_ICON_PRESET,
    CONF_TITLE,
    DOMAIN,
    INTEGRATION_TITLE,
    MAX_TITLE_LENGTH,
    clean_string,
)
from .presets import load_preset_catalog

_LOGGER = logging.getLogger(__name__)


class FaviconConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for favicon. Later changes go through the sidebar panel."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        catalog = await self.hass.async_add_executor_job(load_preset_catalog)
        if not catalog:
            _LOGGER.error("Config flow aborted: no valid shipped presets available")
            return self.async_abort(reason="no_presets_available")

        if user_input is not None:
            # The schema below already rejects unknown presets and long titles.
            return self.async_create_entry(
                title=INTEGRATION_TITLE,
                data={
                    CONF_TITLE: clean_string(user_input.get(CONF_TITLE)) or "",
                    CONF_ICON_PRESET: user_input[CONF_ICON_PRESET],
                    CONF_CUSTOM_ICON_PATH: "",
                },
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_TITLE): vol.All(str, vol.Length(max=MAX_TITLE_LENGTH)),
                vol.Required(CONF_ICON_PRESET): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=preset["id"], label=preset["name"])
                            for preset in catalog
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_ICON_PRESET: catalog[0]["id"]}
            ),
        )
