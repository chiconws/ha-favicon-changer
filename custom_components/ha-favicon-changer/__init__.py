"""Home Assistant integration to change title and favicons."""

from __future__ import annotations

import html
import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aiohttp import web
import homeassistant.components.frontend as frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CUSTOM_ICON_PATH,
    CONF_ICON_PRESET,
    CONF_TITLE,
    CUSTOM_ICON_PUBLIC_ROOT,
    CUSTOM_ICON_STORAGE_ROOT,
    DEFAULT_MANIFEST_NAME,
    DEFAULT_MANIFEST_SHORT_NAME,
    DOMAIN,
    INTEGRATION_TITLE,
    PRESET_PUBLIC_ROOT,
    PRESET_STORAGE_ROOT,
)
from .presets import (
    cleanup_preset_storage,
    get_preset_file_path,
    resolve_preset_icon_path,
)
from .panel import async_register_favicon_panel, async_remove_favicon_panel

_LOGGER = logging.getLogger(__name__)

_RE_APPLE = re.compile(r"^favicon-apple-", re.IGNORECASE)
_RE_ICON = re.compile(r"^favicon-(\d+x\d+)\.([a-z0-9]+)$", re.IGNORECASE)
_ICON_MIME_BY_EXTENSION = {
    "avif": "image/avif",
    "gif": "image/gif",
    "ico": "image/x-icon",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "svg": "image/svg+xml",
    "webp": "image/webp",
}

DATA_GET_TEMPLATE = "get_template"
DATA_MANIFEST_ICONS = "manifest_icons"
DATA_MANIFEST_NAME = "manifest_name"
DATA_MANIFEST_SHORT_NAME = "manifest_short_name"
DATA_YAML_CONFIG = "yaml_config"
DATA_ENTRY_CONFIG = "entry_config"
_TEMPLATE_BASE_RENDER_ATTR = "_ha_favicon_changer_base_render"


class PresetIconView(HomeAssistantView):
    """Serve favicon preset assets without depending on /local."""

    url = f"{PRESET_PUBLIC_ROOT}/{{preset_id}}/{{filename}}"
    name = "api:ha-favicon-changer:presets"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, preset_id: str, filename: str) -> web.FileResponse:
        del request
        file_path = await self.hass.async_add_executor_job(
            get_preset_file_path,
            self.hass,
            preset_id,
            filename,
        )
        if file_path is None:
            raise web.HTTPNotFound()
        return web.FileResponse(file_path)


def _clean_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _normalize_config(config: Mapping[str, Any] | None) -> dict[str, str | None]:
    if not isinstance(config, Mapping):
        config = {}

    title = _clean_string((config or {}).get(CONF_TITLE))
    icon_preset = _clean_string((config or {}).get(CONF_ICON_PRESET))
    custom_icon_path = _clean_string((config or {}).get(CONF_CUSTOM_ICON_PATH))

    return {
        CONF_TITLE: title,
        CONF_ICON_PRESET: icon_preset,
        CONF_CUSTOM_ICON_PATH: custom_icon_path,
    }


def _entry_to_config(config_entry: ConfigEntry) -> dict[str, str | None]:
    merged: dict[str, Any] = dict(config_entry.data)
    merged.update(config_entry.options)
    return _normalize_config(merged)


def _get_manifest_value(key: str, default: Any) -> Any:
    try:
        return frontend.MANIFEST_JSON[key]
    except (KeyError, TypeError):
        _LOGGER.debug("MANIFEST_JSON missing key '%s'; using default", key)
        return default


def _ensure_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    if DOMAIN in hass.data:
        return hass.data[DOMAIN]

    manifest_name = str(_get_manifest_value("name", DEFAULT_MANIFEST_NAME))
    manifest_short_name = str(
        _get_manifest_value("short_name", DEFAULT_MANIFEST_SHORT_NAME)
    )
    manifest_icons = _get_manifest_value("icons", [])
    if not isinstance(manifest_icons, list):
        manifest_icons = []

    hass.data[DOMAIN] = {
        DATA_GET_TEMPLATE: frontend.IndexView.get_template,
        DATA_MANIFEST_ICONS: list(manifest_icons),
        DATA_MANIFEST_NAME: manifest_name,
        DATA_MANIFEST_SHORT_NAME: manifest_short_name,
        DATA_YAML_CONFIG: None,
        DATA_ENTRY_CONFIG: None,
    }
    hass.http.register_view(PresetIconView(hass))
    return hass.data[DOMAIN]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration from YAML."""
    data = _ensure_domain_data(hass)
    _LOGGER.debug("Initializing integration '%s' from YAML", DOMAIN)

    if DOMAIN in config:
        data[DATA_YAML_CONFIG] = _normalize_config(config.get(DOMAIN))
        _LOGGER.info(
            "Loaded YAML config (title_set=%s, preset=%s)",
            bool(data[DATA_YAML_CONFIG].get(CONF_TITLE)),
            data[DATA_YAML_CONFIG].get(CONF_ICON_PRESET),
        )
        await _apply_active_config(hass)
    else:
        _LOGGER.debug("No YAML config found for '%s'", DOMAIN)

    await async_register_favicon_panel(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up integration from a config entry."""
    data = _ensure_domain_data(hass)
    _LOGGER.info("Setting up config entry %s", config_entry.entry_id)

    if not config_entry.title or config_entry.title == "Favicon":
        hass.config_entries.async_update_entry(config_entry, title=INTEGRATION_TITLE)

    config_entry.async_on_unload(config_entry.add_update_listener(_update_listener))
    data[DATA_ENTRY_CONFIG] = _entry_to_config(config_entry)
    _LOGGER.debug(
        "Config entry resolved (title_set=%s, preset=%s)",
        bool(data[DATA_ENTRY_CONFIG].get(CONF_TITLE)),
        data[DATA_ENTRY_CONFIG].get(CONF_ICON_PRESET),
    )

    await async_register_favicon_panel(hass)
    return await _apply_active_config(hass)


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading config entry %s", config_entry.entry_id)
    del config_entry
    data = _ensure_domain_data(hass)
    data[DATA_ENTRY_CONFIG] = None
    result = await _apply_active_config(hass)
    if data.get(DATA_YAML_CONFIG) is None:
        async_remove_favicon_panel(hass)
    return result


async def async_remove_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle config entry removal."""
    _LOGGER.info("Removing config entry %s", config_entry.entry_id)
    del config_entry
    data = _ensure_domain_data(hass)
    data[DATA_ENTRY_CONFIG] = None
    result = await _apply_active_config(hass)
    if data.get(DATA_YAML_CONFIG) is None:
        async_remove_favicon_panel(hass)
    return result


async def _update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle config entry updates."""
    _LOGGER.info("Config entry %s updated", config_entry.entry_id)
    data = _ensure_domain_data(hass)
    data[DATA_ENTRY_CONFIG] = _entry_to_config(config_entry)
    _LOGGER.debug(
        "Updated config resolved (title_set=%s, preset=%s)",
        bool(data[DATA_ENTRY_CONFIG].get(CONF_TITLE)),
        data[DATA_ENTRY_CONFIG].get(CONF_ICON_PRESET),
    )
    await _apply_active_config(hass)


def _active_config(data: Mapping[str, Any]) -> dict[str, str | None]:
    if data.get(DATA_ENTRY_CONFIG) is not None:
        return data[DATA_ENTRY_CONFIG]
    if data.get(DATA_YAML_CONFIG) is not None:
        return data[DATA_YAML_CONFIG]
    return {
        CONF_TITLE: None,
        CONF_ICON_PRESET: None,
        CONF_CUSTOM_ICON_PATH: None,
    }


async def _resolve_icon_path(
    hass: HomeAssistant, config: Mapping[str, str | None]
) -> str | None:
    custom_icon_path = config.get(CONF_CUSTOM_ICON_PATH)
    if custom_icon_path:
        if custom_icon_path.startswith(CUSTOM_ICON_PUBLIC_ROOT):
            _LOGGER.info("Using custom uploaded icon from path '%s'", custom_icon_path)
            removed = await hass.async_add_executor_job(cleanup_preset_storage, hass)
            if removed:
                _LOGGER.info(
                    "Removed %d cached preset folder(s) because a custom icon is active",
                    removed,
                )
            return custom_icon_path
        _LOGGER.warning("Ignoring unsupported custom icon path: %s", custom_icon_path)

    preset_id = config.get(CONF_ICON_PRESET)
    if preset_id:
        _LOGGER.debug("Resolving preset '%s' into local icon path", preset_id)
        resolved = await hass.async_add_executor_job(
            resolve_preset_icon_path,
            hass,
            preset_id,
        )
        if resolved:
            _LOGGER.info("Using icon preset '%s' from path '%s'", preset_id, resolved)
            return resolved
        _LOGGER.warning("Preset '%s' failed to resolve", preset_id)

    removed = await hass.async_add_executor_job(cleanup_preset_storage, hass)
    if removed:
        _LOGGER.info(
            "Removed %d cached preset folder(s) because no preset is currently active",
            removed,
        )

    _LOGGER.debug("No icon preset configured")
    return None


def _join_frontend_path(path: str, filename: str, version: int | None = None) -> str:
    url = f"{path.rstrip('/')}/{filename}"
    if version is None:
        return url
    return f"{url}?v={version}"


def _safe_relative_parts(relative_path: str) -> list[str] | None:
    parts = [part for part in Path(relative_path).parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    return parts


def _mime_type_for_icon(filename: str) -> str | None:
    extension = Path(filename).suffix.lower().lstrip(".")
    return _ICON_MIME_BY_EXTENSION.get(extension)


def find_icons(hass: HomeAssistant, path: str | None) -> dict[str, Any]:
    """Find favicon files in a managed or legacy /local directory."""
    icons: dict[str, Any] = {}
    manifest: list[dict[str, str]] = []

    if not path:
        return icons

    if path.startswith(PRESET_PUBLIC_ROOT):
        relative_path = path[len(PRESET_PUBLIC_ROOT) :].lstrip("/")
        relative_parts = _safe_relative_parts(relative_path)
        if relative_parts is None:
            _LOGGER.warning("Ignoring unsafe preset icon path: %s", path)
            return icons
        local_dir = Path(hass.config.path(*PRESET_STORAGE_ROOT, *relative_parts))
    elif path.startswith(CUSTOM_ICON_PUBLIC_ROOT):
        relative_path = path[len(CUSTOM_ICON_PUBLIC_ROOT) :].lstrip("/")
        relative_parts = _safe_relative_parts(relative_path)
        if relative_parts is None:
            _LOGGER.warning("Ignoring unsafe custom icon path: %s", path)
            return icons
        local_dir = Path(hass.config.path(*CUSTOM_ICON_STORAGE_ROOT, *relative_parts))
    elif path.startswith("/local"):
        local_subpath = path[len("/local") :].lstrip("/")
        local_dir = Path(hass.config.path("www", local_subpath))
    else:
        if path:
            _LOGGER.warning("Ignoring unsupported icon path: %s", path)
        return icons

    _LOGGER.info("Looking for icons in: %s", local_dir)

    try:
        entries = list(local_dir.iterdir())
    except OSError as err:
        _LOGGER.warning("Could not read icon directory %s: %s", local_dir, err)
        return icons

    for entry in entries:
        if not entry.is_file():
            continue

        filename = entry.name
        try:
            mtime = entry.stat().st_mtime_ns
        except OSError:
            mtime = None
        icon_url = _join_frontend_path(path, filename, mtime)

        if filename.lower() == "favicon.ico":
            icons["favicon"] = icon_url
            _LOGGER.info("Found favicon: %s", icon_url)
            continue

        if _RE_APPLE.search(filename):
            icons["apple"] = icon_url
            _LOGGER.info("Found apple icon: %s", icon_url)
            continue

        icon_match = _RE_ICON.search(filename)
        if icon_match:
            mime_type = _mime_type_for_icon(filename)
            if not mime_type:
                _LOGGER.debug("Skipping manifest icon with unsupported type: %s", filename)
                continue
            manifest.append(
                {
                    "src": icon_url,
                    "sizes": icon_match.group(1),
                    "type": mime_type,
                }
            )
            _LOGGER.info("Found icon: %s", icon_url)

    if manifest:
        manifest.sort(key=lambda item: int(item["sizes"].split("x", 1)[0]))
        icons["manifest"] = manifest

    if "favicon" not in icons and manifest:
        icons["favicon"] = manifest[0]["src"]
        _LOGGER.info("No favicon.ico found; using icon fallback: %s", icons["favicon"])

    if not icons:
        _LOGGER.warning(
            "No supported icon files found in %s. Expected favicon.ico, favicon-apple-*.png, or favicon-<size>x<size>.<ext>",
            local_dir,
        )
    else:
        _LOGGER.info(
            "Icon scan summary (favicon=%s, apple=%s, manifest_icons=%d)",
            "favicon" in icons,
            "apple" in icons,
            len(icons.get("manifest", [])),
        )

    return icons


def _clear_frontend_template_cache(hass: HomeAssistant) -> None:
    if not hasattr(hass, "http"):
        return

    cleared = 0
    for view in hass.http.app.router.resources():
        if isinstance(view, frontend.IndexView):
            view._template_cache = None
            cleared += 1

    if hasattr(frontend, "_async_render_index_cached"):
        frontend._async_render_index_cached.cache_clear()
    _LOGGER.debug("Cleared template cache for %d frontend views", cleared)


async def _apply_active_config(hass: HomeAssistant) -> bool:
    data = _ensure_domain_data(hass)
    config = _active_config(data)

    resolved_icon_path = await _resolve_icon_path(hass, config)
    icons = await hass.async_add_executor_job(find_icons, hass, resolved_icon_path)
    title = config.get(CONF_TITLE)
    _LOGGER.debug(
        "Applying config (title_set=%s, preset=%s, icons_found=%s)",
        bool(title),
        config.get(CONF_ICON_PRESET),
        bool(icons),
    )

    if not title and not icons:
        _LOGGER.info("No title or icons active; restoring default frontend values")
        return remove_hooks(hass)

    def _get_template(self: frontend.IndexView):
        template = data[DATA_GET_TEMPLATE](self)
        base_render = getattr(template, _TEMPLATE_BASE_RENDER_ATTR, None)
        if base_render is None:
            base_render = template.render
            setattr(template, _TEMPLATE_BASE_RENDER_ATTR, base_render)

        def new_render(*args: Any, **kwargs: Any) -> str:
            text = base_render(*args, **kwargs)
            if "favicon" in icons:
                text = text.replace("/static/icons/favicon.ico", icons["favicon"])
            if "apple" in icons:
                text = text.replace(
                    "/static/icons/favicon-apple-180x180.png",
                    icons["apple"],
                )
            if "favicon" in icons:
                text = text.replace(
                    "</head>",
                    (
                        f'<link rel="shortcut icon" href="{icons["favicon"]}">'
                        "</head>"
                    ),
                )
            if "manifest" in icons:
                text = text.replace(
                    "</head>",
                    (
                        f'<link rel="icon" type="{icons["manifest"][0]["type"]}" href="{icons["manifest"][0]["src"]}">'
                        "</head>"
                    ),
                )
            if title:
                escaped_title = html.escape(title)
                script_title = json.dumps(title).replace("</", "<\\/")

                text = text.replace(
                    "<title>Home Assistant</title>",
                    f"<title>{escaped_title}</title>",
                )
                text = text.replace(
                    "</head>",
                    (
                        "<script type=\"module\">"
                        f"const customTitle = {script_title};"
                        "const rewriteTitle = () => {"
                        "if (document.title.includes('Home Assistant')) {"
                        "document.title = document.title.replace(/Home Assistant/g, customTitle);"
                        "} else if (!document.title) {"
                        "document.title = customTitle;"
                        "}"
                        "};"
                        "rewriteTitle();"
                        "window.setInterval(rewriteTitle, 1000);"
                        "</script></head>"
                    ),
                )

            return text

        template.render = new_render
        return template

    frontend.IndexView.get_template = _get_template
    _clear_frontend_template_cache(hass)

    if "manifest" in icons:
        frontend.add_manifest_json_key("icons", icons["manifest"])
    else:
        frontend.add_manifest_json_key("icons", data[DATA_MANIFEST_ICONS].copy())

    if title:
        frontend.add_manifest_json_key("name", title)
        frontend.add_manifest_json_key("short_name", title)
    else:
        frontend.add_manifest_json_key("name", data[DATA_MANIFEST_NAME])
        frontend.add_manifest_json_key("short_name", data[DATA_MANIFEST_SHORT_NAME])

    _LOGGER.info(
        "Applied frontend hooks (title_set=%s, favicon=%s, apple=%s, manifest_icons=%d)",
        bool(title),
        "favicon" in icons,
        "apple" in icons,
        len(icons.get("manifest", [])),
    )

    return True


def remove_hooks(hass: HomeAssistant) -> bool:
    """Restore original frontend hooks and manifest values."""
    data = hass.data.get(DOMAIN)
    if not data:
        return True

    frontend.IndexView.get_template = data[DATA_GET_TEMPLATE]
    frontend.add_manifest_json_key("icons", data[DATA_MANIFEST_ICONS].copy())
    frontend.add_manifest_json_key("name", data[DATA_MANIFEST_NAME])
    frontend.add_manifest_json_key("short_name", data[DATA_MANIFEST_SHORT_NAME])
    _clear_frontend_template_cache(hass)
    _LOGGER.info("Removed frontend hooks and restored default manifest values")

    return True
