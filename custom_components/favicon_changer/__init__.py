"""Home Assistant integration to change title and favicons."""

from __future__ import annotations

import contextlib
import html
import json
import logging
import mimetypes
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import homeassistant.components.frontend as frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CUSTOM_ICON_PATH,
    CONF_ICON_PRESET,
    CONF_TITLE,
    CUSTOM_ICON_PUBLIC_PATH,
    DOMAIN,
    INTEGRATION_TITLE,
    PRESET_PUBLIC_ROOT,
    clean_string,
    entry_values,
)
from .custom_icons import custom_icon_dir
from .panel import async_register_favicon_panel, async_remove_favicon_panel
from .presets import PRESETS_PATH

_LOGGER = logging.getLogger(__name__)

_RE_APPLE = re.compile(r"^favicon-apple-", re.IGNORECASE)
_RE_ICON = re.compile(r"^favicon-(\d+x\d+)\.([a-z0-9]+)$", re.IGNORECASE)
# Python < 3.13 only knows .webp when the OS ships a mime.types file.
mimetypes.add_type("image/webp", ".webp")

DATA_GET_TEMPLATE = "get_template"
DATA_MANIFEST = "manifest"
_MANIFEST_KEYS = ("icons", "name", "short_name")
_TEMPLATE_BASE_RENDER_ATTR = "_favicon_changer_base_render"


def _ensure_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    data = hass.data.setdefault(DOMAIN, {})
    if DATA_GET_TEMPLATE not in data:
        data[DATA_GET_TEMPLATE] = frontend.IndexView.get_template
        data[DATA_MANIFEST] = {key: frontend.MANIFEST_JSON[key] for key in _MANIFEST_KEYS}
    return data


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up integration from a config entry."""
    _ensure_domain_data(hass)
    _LOGGER.info("Setting up config entry %s", config_entry.entry_id)

    if not config_entry.title or config_entry.title == "Favicon":
        hass.config_entries.async_update_entry(config_entry, title=INTEGRATION_TITLE)

    config_entry.async_on_unload(config_entry.add_update_listener(_update_listener))
    await async_register_favicon_panel(hass)
    await _apply_config(hass, entry_values(config_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading config entry %s", config_entry.entry_id)
    remove_hooks(hass)
    async_remove_favicon_panel(hass)
    return True


async def _update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle config entry updates."""
    _LOGGER.info("Config entry %s updated", config_entry.entry_id)
    await _apply_config(hass, entry_values(config_entry))


def _icon_source(
    hass: HomeAssistant, config: Mapping[str, Any]
) -> tuple[str, Path] | None:
    """Return the public URL path and local directory of the active icons."""
    if clean_string(config.get(CONF_CUSTOM_ICON_PATH)):
        return CUSTOM_ICON_PUBLIC_PATH, custom_icon_dir(hass)
    if preset_id := clean_string(config.get(CONF_ICON_PRESET)):
        return f"{PRESET_PUBLIC_ROOT}/{preset_id}/", PRESETS_PATH / preset_id
    return None


def find_icons(public_path: str, local_dir: Path) -> dict[str, Any]:
    """Find favicon files in local_dir and map them to public URLs."""
    icons: dict[str, Any] = {}
    manifest: list[dict[str, str]] = []

    try:
        entries = list(local_dir.iterdir())
    except OSError as err:
        _LOGGER.warning("Could not read icon directory %s: %s", local_dir, err)
        return icons

    for entry in entries:
        if not entry.is_file():
            continue

        filename = entry.name
        icon_url = f"{public_path}{filename}"
        with contextlib.suppress(OSError):
            icon_url = f"{icon_url}?v={entry.stat().st_mtime_ns}"

        if filename.lower() == "favicon.ico":
            icons["favicon"] = icon_url
            continue

        if _RE_APPLE.search(filename):
            icons["apple"] = icon_url
            continue

        icon_match = _RE_ICON.search(filename)
        if icon_match:
            mime_type = mimetypes.guess_type(filename)[0]
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

    if manifest:
        manifest.sort(key=lambda item: int(item["sizes"].split("x", 1)[0]))
        icons["manifest"] = manifest

    if "favicon" not in icons and manifest:
        icons["favicon"] = manifest[0]["src"]

    if not icons:
        _LOGGER.warning(
            "No supported icon files found in %s. Expected favicon.ico, favicon-apple-*.png, or favicon-<size>x<size>.<ext>",
            local_dir,
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


async def _apply_config(hass: HomeAssistant, config: Mapping[str, Any]) -> None:
    data = _ensure_domain_data(hass)

    source = _icon_source(hass, config)
    icons = await hass.async_add_executor_job(find_icons, *source) if source else {}
    title = clean_string(config.get(CONF_TITLE))
    _LOGGER.debug(
        "Applying config (title_set=%s, preset=%s, icons_found=%s)",
        bool(title),
        config.get(CONF_ICON_PRESET),
        bool(icons),
    )

    if not title and not icons:
        _LOGGER.info("No title or icons active; restoring default frontend values")
        remove_hooks(hass)
        return

    def _get_template(self: frontend.IndexView):
        template = data[DATA_GET_TEMPLATE](self)
        base_render = getattr(template, _TEMPLATE_BASE_RENDER_ATTR, None)
        if base_render is None:
            base_render = template.render
            setattr(template, _TEMPLATE_BASE_RENDER_ATTR, base_render)

        def new_render(*args: Any, **kwargs: Any) -> str:
            text = base_render(*args, **kwargs)
            head = ""
            if "favicon" in icons:
                text = text.replace("/static/icons/favicon.ico", icons["favicon"])
                head += f'<link rel="shortcut icon" href="{icons["favicon"]}">'
            if "apple" in icons:
                text = text.replace(
                    "/static/icons/favicon-apple-180x180.png", icons["apple"]
                )
            if "manifest" in icons:
                first = icons["manifest"][0]
                head += f'<link rel="icon" type="{first["type"]}" href="{first["src"]}">'
            if title:
                script_title = json.dumps(title).replace("<", "\\u003c")
                text = text.replace(
                    "<title>Home Assistant</title>",
                    f"<title>{html.escape(title)}</title>",
                )
                head += (
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
                    "</script>"
                )
            return text.replace("</head>", f"{head}</head>")

        template.render = new_render
        return template

    setattr(frontend.IndexView, "get_template", _get_template)  # noqa: B010 - patching is the feature
    _clear_frontend_template_cache(hass)

    manifest = data[DATA_MANIFEST]
    frontend.add_manifest_json_key("icons", icons.get("manifest", manifest["icons"]))
    frontend.add_manifest_json_key("name", title or manifest["name"])
    frontend.add_manifest_json_key("short_name", title or manifest["short_name"])

    _LOGGER.info(
        "Applied frontend hooks (title_set=%s, favicon=%s, apple=%s, manifest_icons=%d)",
        bool(title),
        "favicon" in icons,
        "apple" in icons,
        len(icons.get("manifest", [])),
    )


def remove_hooks(hass: HomeAssistant) -> None:
    """Restore original frontend hooks and manifest values."""
    data = hass.data.get(DOMAIN)
    if not data or DATA_GET_TEMPLATE not in data:
        return

    setattr(frontend.IndexView, "get_template", data[DATA_GET_TEMPLATE])  # noqa: B010
    for key, value in data[DATA_MANIFEST].items():
        frontend.add_manifest_json_key(key, value)
    _clear_frontend_template_cache(hass)
    _LOGGER.info("Removed frontend hooks and restored default manifest values")
