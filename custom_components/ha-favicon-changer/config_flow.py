"""Config flow for favicon integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
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
)
from .presets import PresetInfo, get_preset_ids, load_preset_catalog

_LOGGER = logging.getLogger(__name__)

_CUSTOM_UPLOAD_OPTION = "__custom_upload__"


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


async def _async_load_preset_catalog(hass: HomeAssistant) -> tuple[PresetInfo, ...]:
    catalog = await hass.async_add_executor_job(load_preset_catalog)
    if not catalog:
        _LOGGER.warning("No valid shipped presets were discovered")
    return catalog


def _preset_selector(
    catalog: tuple[PresetInfo, ...], *, include_custom_upload: bool
) -> SelectSelector:
    options: list[SelectOptionDict] = []
    if include_custom_upload:
        options.append(
            SelectOptionDict(
                value=_CUSTOM_UPLOAD_OPTION,
                label="Custom upload (keep current)",
            )
        )

    options.extend(
        SelectOptionDict(value=preset["id"], label=preset["name"])
        for preset in catalog
    )

    _LOGGER.debug("Building preset selector with %d shipped presets", len(catalog))
    return SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
    )


def _current_values(config_entry: ConfigEntry) -> dict[str, Any]:
    values = dict(config_entry.data)
    values.update(config_entry.options)
    return values


def _build_main_schema(
    flow: config_entries.ConfigFlow | config_entries.OptionsFlow,
    current_values: Mapping[str, Any] | None,
    catalog: tuple[PresetInfo, ...],
) -> vol.Schema:
    current_values = current_values or {}

    suggested_values: dict[str, Any] = {}
    if CONF_TITLE in current_values:
        suggested_values[CONF_TITLE] = current_values[CONF_TITLE]

    custom_icon_path = _clean_string(current_values.get(CONF_CUSTOM_ICON_PATH))
    icon_preset = _clean_string(current_values.get(CONF_ICON_PRESET))
    if custom_icon_path:
        icon_preset = _CUSTOM_UPLOAD_OPTION
    elif not icon_preset and catalog:
        icon_preset = catalog[0]["id"]
    if icon_preset:
        suggested_values[CONF_ICON_PRESET] = icon_preset

    schema = vol.Schema(
        {
            vol.Optional(CONF_TITLE): vol.All(str, vol.Length(max=MAX_TITLE_LENGTH)),
            vol.Required(CONF_ICON_PRESET): _preset_selector(
                catalog, include_custom_upload=bool(custom_icon_path)
            ),
        }
    )
    return flow.add_suggested_values_to_schema(schema, suggested_values)


def _validate_main_step(
    user_input: Mapping[str, Any],
    valid_preset_ids: set[str],
    *,
    current_custom_icon_path: str | None = None,
) -> tuple[str, str, str | None, dict[str, str]]:
    errors: dict[str, str] = {}

    title = _clean_string(user_input.get(CONF_TITLE)) or ""
    if len(title) > MAX_TITLE_LENGTH:
        errors[CONF_TITLE] = "title_too_long"

    icon_preset = _clean_string(user_input.get(CONF_ICON_PRESET)) or ""
    if icon_preset == _CUSTOM_UPLOAD_OPTION and current_custom_icon_path:
        return title, "", current_custom_icon_path, errors

    if icon_preset not in valid_preset_ids:
        _LOGGER.warning("User selected invalid icon preset: %s", icon_preset)
        errors[CONF_ICON_PRESET] = "invalid_preset"

    return title, icon_preset, None, errors


def _build_entry_data(
    title: str, icon_preset: str, custom_icon_path: str | None
) -> dict[str, str]:
    output: dict[str, str] = {CONF_TITLE: title}
    output[CONF_ICON_PRESET] = icon_preset
    output[CONF_CUSTOM_ICON_PATH] = custom_icon_path or ""
    return output


def _log_saved_config(action: str, data: Mapping[str, Any]) -> None:
    _LOGGER.info(
        "%s (title_set=%s, preset=%s, custom_icon=%s)",
        action,
        bool(_clean_string(data.get(CONF_TITLE))),
        _clean_string(data.get(CONF_ICON_PRESET)),
        bool(_clean_string(data.get(CONF_CUSTOM_ICON_PATH))),
    )


class FaviconConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for favicon."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            _LOGGER.info("Config flow aborted: single instance already configured")
            return self.async_abort(reason="single_instance_allowed")

        catalog = await _async_load_preset_catalog(self.hass)
        valid_preset_ids = get_preset_ids(catalog)
        if not valid_preset_ids:
            _LOGGER.error("Config flow aborted: no valid shipped presets available")
            return self.async_abort(reason="no_presets_available")

        errors: dict[str, str] = {}
        if user_input is not None:
            title, icon_preset, custom_icon_path, errors = _validate_main_step(
                user_input, valid_preset_ids
            )
            if not errors:
                data = _build_entry_data(title, icon_preset, custom_icon_path)
                _log_saved_config("Creating config entry", data)
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=INTEGRATION_TITLE, data=data)

            _LOGGER.warning("Config flow validation failed with errors: %s", errors)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_main_schema(self, user_input, catalog),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        del config_entry
        return FaviconOptionsFlow()


class FaviconOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for favicon."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        catalog = await _async_load_preset_catalog(self.hass)
        valid_preset_ids = get_preset_ids(catalog)
        if not valid_preset_ids:
            _LOGGER.error("Options flow aborted: no valid shipped presets available")
            return self.async_abort(reason="no_presets_available")

        errors: dict[str, str] = {}
        stored_values = _current_values(self.config_entry)
        current_custom_icon_path = _clean_string(stored_values.get(CONF_CUSTOM_ICON_PATH))

        if user_input is not None:
            title, icon_preset, custom_icon_path, errors = _validate_main_step(
                user_input,
                valid_preset_ids,
                current_custom_icon_path=current_custom_icon_path,
            )
            if not errors:
                data = _build_entry_data(title, icon_preset, custom_icon_path)
                _log_saved_config("Saving options", data)
                return self.async_create_entry(title="", data=data)

            _LOGGER.warning("Options flow validation failed with errors: %s", errors)
            current_values = dict(stored_values)
            current_values.update(user_input)
        else:
            current_values = stored_values

        return self.async_show_form(
            step_id="init",
            data_schema=_build_main_schema(self, current_values, catalog),
            errors=errors,
        )
