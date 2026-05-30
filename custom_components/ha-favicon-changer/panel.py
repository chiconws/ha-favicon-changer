"""Home Assistant panel and API views for favicon selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.multipart import BodyPartReader

from homeassistant.components import frontend, panel_custom
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.http import HomeAssistantView

from .const import (
    CONF_CUSTOM_ICON_PATH,
    CONF_ICON_PRESET,
    CONF_TITLE,
    CUSTOM_ICON_PUBLIC_ROOT,
    DOMAIN,
    INTEGRATION_TITLE,
    MAX_TITLE_LENGTH,
    MAX_UPLOAD_BYTES,
    PRESET_PUBLIC_ROOT,
)
from .custom_icons import (
    CustomIconError,
    get_custom_icon_file_path,
    get_custom_icon_preview_url,
    get_custom_icon_public_path,
    save_custom_icon,
)
from .presets import load_preset_catalog

PANEL_COMPONENT_NAME = "ha-favicon-changer-panel"
PANEL_FRONTEND_URL_PATH = "ha-favicon-changer"
PANEL_MODULE_URL = "/api/ha-favicon-changer/panel.js"
PANEL_MODULE_PATH = Path(__file__).resolve().parent / "frontend" / "favicon-changer-panel.js"
DATA_PANEL_REGISTERED = "panel_registered"
DATA_PANEL_VIEWS_REGISTERED = "panel_views_registered"


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _require_admin(request: web.Request) -> None:
    user = request["hass_user"]
    if not user.is_admin:
        raise Unauthorized()


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _config_entry(hass: HomeAssistant) -> ConfigEntry | None:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return None
    return entries[0]


def _entry_values(config_entry: ConfigEntry | None) -> dict[str, Any]:
    if config_entry is None:
        return {}
    values = dict(config_entry.data)
    values.update(config_entry.options)
    return values


def _validate_title(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("Title must be text.")
    title = value.strip()
    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"Title must be {MAX_TITLE_LENGTH} characters or fewer.")
    return title


async def _async_custom_preview_url(hass: HomeAssistant) -> str | None:
    return await hass.async_add_executor_job(get_custom_icon_preview_url, hass)


async def async_panel_payload(hass: HomeAssistant) -> dict[str, Any]:
    """Return data used by the frontend panel."""
    config_entry = _config_entry(hass)
    values = _entry_values(config_entry)
    title = _clean_string(values.get(CONF_TITLE)) or ""
    icon_preset = _clean_string(values.get(CONF_ICON_PRESET)) or ""
    custom_icon_path = _clean_string(values.get(CONF_CUSTOM_ICON_PATH))

    catalog = await hass.async_add_executor_job(load_preset_catalog)
    custom_preview_url = await _async_custom_preview_url(hass)
    custom_active = bool(custom_icon_path and custom_preview_url)

    return {
        "writable": config_entry is not None,
        "title": title,
        "icon_source": "custom" if custom_active else "preset",
        "icon_preset": "" if custom_active else icon_preset,
        "custom_icon_url": custom_preview_url,
        "limits": {
            "max_bytes": MAX_UPLOAD_BYTES,
            "accepted_types": [
                "image/gif",
                "image/jpeg",
                "image/png",
                "image/x-icon",
                "image/vnd.microsoft.icon",
                "image/webp",
            ],
            "accepted_extensions": [
                ".png",
                ".ico",
                ".webp",
                ".gif",
                ".jpg",
                ".jpeg",
            ],
            "png_min_size": 64,
            "ico_min_size": 16,
            "webp_min_size": 64,
            "gif_min_size": 64,
            "jpeg_min_size": 64,
            "max_size": 1024,
        },
        "presets": [
            {
                "id": preset["id"],
                "name": preset["name"],
                "preview_url": (
                    f"{PRESET_PUBLIC_ROOT}/{preset['id']}/favicon-512x512.png"
                ),
                "active": not custom_active and icon_preset == preset["id"],
            }
            for preset in catalog
        ],
    }


async def _async_update_entry_options(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    *,
    title: str,
    icon_preset: str,
    custom_icon_path: str | None,
) -> None:
    options = dict(config_entry.options)
    options[CONF_TITLE] = title
    options[CONF_ICON_PRESET] = icon_preset
    options[CONF_CUSTOM_ICON_PATH] = custom_icon_path or ""
    hass.config_entries.async_update_entry(config_entry, options=options)


class FaviconPanelModuleView(HomeAssistantView):
    """Serve the frontend module for the favicon panel."""

    url = PANEL_MODULE_URL
    name = "api:ha-favicon-changer:panel-module"
    requires_auth = False

    async def get(self, request: web.Request) -> web.FileResponse:
        del request
        return web.FileResponse(PANEL_MODULE_PATH)


class FaviconPanelConfigView(HomeAssistantView):
    """Expose preset metadata and save the active favicon selection."""

    url = "/api/ha-favicon-changer/config"
    name = "api:ha-favicon-changer:config"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        return web.json_response(await async_panel_payload(hass))

    async def post(self, request: web.Request) -> web.Response:
        _require_admin(request)
        hass: HomeAssistant = request.app["hass"]
        config_entry = _config_entry(hass)
        if config_entry is None:
            return _json_error("Create the Favicon Changer integration before saving.")

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return _json_error("Request body must be JSON.")
        if not isinstance(body, dict):
            return _json_error("Request body must be an object.")

        try:
            title = _validate_title(body.get(CONF_TITLE))
        except ValueError as err:
            return _json_error(str(err))

        source = _clean_string(body.get("source")) or "preset"
        if source == "custom":
            if await _async_custom_preview_url(hass) is None:
                return _json_error("Upload a custom icon before selecting it.")
            await _async_update_entry_options(
                hass,
                config_entry,
                title=title,
                icon_preset="",
                custom_icon_path=get_custom_icon_public_path(),
            )
            return web.json_response(await async_panel_payload(hass))

        if source != "preset":
            return _json_error("Unknown icon source.")

        icon_preset = _clean_string(body.get(CONF_ICON_PRESET)) or ""
        catalog = await hass.async_add_executor_job(load_preset_catalog)
        valid_preset_ids = {preset["id"] for preset in catalog}
        if icon_preset not in valid_preset_ids:
            return _json_error("Choose a valid icon preset.")

        await _async_update_entry_options(
            hass,
            config_entry,
            title=title,
            icon_preset=icon_preset,
            custom_icon_path=None,
        )
        return web.json_response(await async_panel_payload(hass))


class FaviconPanelUploadView(HomeAssistantView):
    """Handle custom favicon uploads."""

    url = "/api/ha-favicon-changer/upload"
    name = "api:ha-favicon-changer:upload"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        _require_admin(request)
        hass: HomeAssistant = request.app["hass"]
        config_entry = _config_entry(hass)
        if config_entry is None:
            return _json_error("Create the Favicon Changer integration before uploading.")

        if request.content_length and request.content_length > MAX_UPLOAD_BYTES + 4096:
            return _json_error("Icon is larger than 1 MiB.", status=413)

        try:
            reader = await request.multipart()
        except ValueError:
            return _json_error("Upload must use multipart form data.")

        filename: str | None = None
        content_type: str | None = None
        content = b""
        title_from_form: str | None = None

        while field := await reader.next():
            if not isinstance(field, BodyPartReader):
                continue
            if field.name == CONF_TITLE:
                title_from_form = await field.text()
                continue
            if field.name != "file":
                continue
            filename = field.filename
            content_type = field.headers.get("Content-Type")
            chunks: list[bytes] = []
            total = 0
            while chunk := await field.read_chunk():
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    return _json_error("Icon is larger than 1 MiB.", status=413)
                chunks.append(chunk)
            content = b"".join(chunks)

        if not content:
            return _json_error("Choose a PNG, ICO, WebP, GIF, or JPEG file to upload.")

        try:
            title = _validate_title(
                title_from_form
                if title_from_form is not None
                else _entry_values(config_entry).get(CONF_TITLE)
            )
            custom_path = await hass.async_add_executor_job(
                save_custom_icon,
                hass,
                filename,
                content_type,
                content,
            )
        except (CustomIconError, ValueError) as err:
            return _json_error(str(err))

        await _async_update_entry_options(
            hass,
            config_entry,
            title=title,
            icon_preset="",
            custom_icon_path=custom_path,
        )
        return web.json_response(await async_panel_payload(hass))


class CustomIconView(HomeAssistantView):
    """Serve custom uploaded favicon assets."""

    url = f"{CUSTOM_ICON_PUBLIC_ROOT}/{{slot}}/{{filename}}"
    name = "api:ha-favicon-changer:custom-icon"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, slot: str, filename: str) -> web.FileResponse:
        del request
        file_path = await self.hass.async_add_executor_job(
            get_custom_icon_file_path,
            self.hass,
            slot,
            filename,
        )
        if file_path is None:
            raise web.HTTPNotFound()
        return web.FileResponse(file_path)


def _register_panel_views(hass: HomeAssistant) -> None:
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_PANEL_VIEWS_REGISTERED):
        return

    hass.http.register_view(FaviconPanelModuleView())
    hass.http.register_view(FaviconPanelConfigView())
    hass.http.register_view(FaviconPanelUploadView())
    hass.http.register_view(CustomIconView(hass))
    data[DATA_PANEL_VIEWS_REGISTERED] = True


async def async_register_favicon_panel(hass: HomeAssistant) -> None:
    """Register the sidebar panel and its API views."""
    _register_panel_views(hass)
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_PANEL_REGISTERED):
        return

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_FRONTEND_URL_PATH,
        webcomponent_name=PANEL_COMPONENT_NAME,
        sidebar_title=INTEGRATION_TITLE,
        sidebar_icon="mdi:image-edit",
        module_url=PANEL_MODULE_URL,
        require_admin=True,
        config_panel_domain=DOMAIN,
    )
    data[DATA_PANEL_REGISTERED] = True


def async_remove_favicon_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel."""
    data = hass.data.setdefault(DOMAIN, {})
    data[DATA_PANEL_REGISTERED] = False
    frontend.async_remove_panel(hass, PANEL_FRONTEND_URL_PATH, warn_if_unknown=False)
