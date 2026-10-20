"""Checks through a running Home Assistant: setup/unload, config flow and the panel API."""

import importlib
import io
from typing import Any
from unittest.mock import patch

import aiohttp
import homeassistant.components.frontend as frontend
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from PIL import Image
from pytest_homeassistant_custom_component.common import CLIENT_ID

DOMAIN = "favicon_changer"
CONFIG_URL = "/api/ha-favicon-changer/config"
UPLOAD_URL = "/api/ha-favicon-changer/upload"


def _png(size: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (size, size)).save(buffer, "PNG")
    return buffer.getvalue()


def _upload_form(content: bytes, filename: str = "icon.png", title: str | None = None):
    form = aiohttp.FormData()
    if title is not None:
        form.add_field("title", title)
    form.add_field("file", content, filename=filename, content_type="image/png")
    return form


async def test_setup_applies_config_and_unload_restores(hass: HomeAssistant, entry):
    original_template = hass.data[DOMAIN]["get_template"]
    assert frontend.MANIFEST_JSON["name"] == "My Home"
    assert frontend.MANIFEST_JSON["icons"][0]["src"].startswith("/api/ha-favicon-changer/presets/beta/")
    assert frontend.IndexView.get_template is not original_template
    assert "ha-favicon-changer" in hass.data[frontend.DATA_PANELS]

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert frontend.MANIFEST_JSON["name"] == "Home Assistant"
    assert frontend.IndexView.get_template is original_template
    assert "ha-favicon-changer" not in hass.data[frontend.DATA_PANELS]


async def test_empty_config_keeps_frontend_defaults(hass: HomeAssistant, entry):
    original_template = hass.data[DOMAIN]["get_template"]
    hass.config_entries.async_update_entry(entry, options={"title": "", "icon_preset": ""})
    await hass.async_block_till_done()
    assert frontend.IndexView.get_template is original_template
    assert frontend.MANIFEST_JSON["name"] == "Home Assistant"


async def test_config_flow_creates_entry(hass: HomeAssistant, http):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"title": "", "icon_preset": "", "custom_icon_path": ""}


async def test_config_flow_aborts_without_presets(hass: HomeAssistant, http):
    config_flow = importlib.import_module("custom_components.favicon_changer.config_flow")
    with patch.object(config_flow, "load_preset_catalog", return_value=()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_presets_available"


async def test_panel_get_and_switch_preset(hass: HomeAssistant, entry, hass_client):
    client = await hass_client()
    payload = await (await client.get(CONFIG_URL)).json()
    assert payload["title"] == "My Home"
    assert payload["icon_source"] == "preset"
    assert [p["id"] for p in payload["presets"] if p["active"]] == ["beta"]
    assert ".png" in payload["limits"]["accepted_extensions"]

    response = await client.post(CONFIG_URL, json={"title": "Casa", "source": "preset", "icon_preset": "dev"})
    assert response.status == 200
    await hass.async_block_till_done()
    assert entry.options["icon_preset"] == "dev"
    assert frontend.MANIFEST_JSON["name"] == "Casa"
    assert frontend.MANIFEST_JSON["icons"][0]["src"].startswith("/api/ha-favicon-changer/presets/dev/")


async def test_panel_post_rejects_bad_input(hass: HomeAssistant, entry, hass_client):
    client = await hass_client()
    cases: list[tuple[dict[str, Any], str]] = [
        ({"data": "not json"}, "Request body must be JSON."),
        ({"json": []}, "Request body must be an object."),
        ({"json": {"title": 5}}, "Title must be text."),
        ({"json": {"title": "x" * 121}}, "Title must be 120 characters or fewer."),
        ({"json": {"source": "other"}}, "Unknown icon source."),
        ({"json": {"source": "preset", "icon_preset": "nope"}}, "Choose a valid icon preset."),
        ({"json": {"source": "custom"}}, "Upload a custom icon before selecting it."),
    ]
    for kwargs, message in cases:
        response = await client.post(CONFIG_URL, **kwargs)
        assert response.status == 400, message
        assert (await response.json())["error"] == message


async def test_panel_requires_admin(hass: HomeAssistant, entry, hass_client, hass_read_only_user):
    refresh_token = await hass.auth.async_create_refresh_token(hass_read_only_user, CLIENT_ID)
    client = await hass_client(hass.auth.async_create_access_token(refresh_token))
    assert (await client.post(CONFIG_URL, json={})).status == 401
    assert (await client.post(UPLOAD_URL, data=_upload_form(_png(64)))).status == 401


async def test_upload_activates_custom_icon(hass: HomeAssistant, entry, hass_client, hass_client_no_auth):
    client = await hass_client()
    response = await client.post(UPLOAD_URL, data=_upload_form(_png(128), title="Casa"))
    assert response.status == 200
    payload = await response.json()
    await hass.async_block_till_done()
    assert payload["icon_source"] == "custom"
    assert payload["title"] == "Casa"
    assert entry.options["custom_icon_path"] == "/api/ha-favicon-changer/custom/"
    assert frontend.MANIFEST_JSON["icons"][0]["src"].startswith("/api/ha-favicon-changer/custom/favicon-128x128.png")

    # Switching away and back to the stored upload works without re-uploading.
    await client.post(CONFIG_URL, json={"source": "preset", "icon_preset": "beta"})
    response = await client.post(CONFIG_URL, json={"source": "custom"})
    assert (await response.json())["icon_source"] == "custom"

    public = await hass_client_no_auth()
    assert (await public.get(payload["custom_icon_url"].split("?")[0])).status == 200
    assert (await public.get("/api/ha-favicon-changer/custom/other/favicon.ico")).status == 404
    assert (await public.get("/api/ha-favicon-changer/presets/beta/favicon.ico")).status == 200
    assert (await public.get("/api/ha-favicon-changer/presets/nope/favicon.ico")).status == 404
    assert (await public.get("/api/ha-favicon-changer/panel.js")).status == 200


async def test_upload_rejects_bad_files(hass: HomeAssistant, entry, hass_client):
    client = await hass_client()
    cases = [
        (_upload_form(b"junk"), 400, "Upload a PNG, ICO, WebP, GIF, or JPEG icon."),
        (_upload_form(b"\0" * (1024 * 1024 + 1)), 413, "Icon is larger than 1 MiB."),
        (aiohttp.FormData({"title": "only a title"}, default_to_multipart=True), 400, "Choose a PNG, ICO, WebP, GIF, or JPEG file to upload."),
    ]
    for data, status, message in cases:
        response = await client.post(UPLOAD_URL, data=data)
        assert response.status == status, message
        assert (await response.json())["error"] == message

    bad_bodies = [
        (b"{}", {"Content-Type": "application/json"}),
        (b"{}", {"Content-Type": "multipart/form-data"}),
        (b"--other\r\n\r\n--other--\r\n", {"Content-Type": "multipart/form-data; boundary=x"}),
    ]
    for body, headers in bad_bodies:
        response = await client.post(UPLOAD_URL, data=body, headers=headers)
        assert response.status == 400
        assert (await response.json())["error"] == "Upload must use multipart form data."


async def test_panel_writes_need_a_config_entry(hass: HomeAssistant, entry, hass_client):
    assert await hass.config_entries.async_remove(entry.entry_id)
    client = await hass_client()
    assert (await (await client.get(CONFIG_URL)).json())["writable"] is False
    response = await client.post(CONFIG_URL, json={})
    assert (await response.json())["error"] == "Create the Favicon Changer integration before saving."
    response = await client.post(UPLOAD_URL, data=_upload_form(_png(64)))
    assert (await response.json())["error"] == "Create the Favicon Changer integration before uploading."

