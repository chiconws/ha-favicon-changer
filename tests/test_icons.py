"""Checks for upload validation, icon discovery and the preset catalog."""

import importlib
import io
from pathlib import Path
from types import SimpleNamespace

import homeassistant.components.frontend as frontend
import pytest
from PIL import Image

integration = importlib.import_module("custom_components.favicon_changer")
custom_icons = importlib.import_module("custom_components.favicon_changer.custom_icons")
presets = importlib.import_module("custom_components.favicon_changer.preset_catalog")
PRESET_PUBLIC_ROOT = importlib.import_module("custom_components.favicon_changer.const").PRESET_PUBLIC_ROOT


def _image(fmt: str, size: tuple[int, int], **kwargs) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA" if fmt in {"PNG", "ICO", "WEBP"} else "RGB", size).save(
        buffer, fmt, **kwargs
    )
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("fmt", "extension"),
    [("PNG", "png"), ("WEBP", "webp"), ("GIF", "gif"), ("JPEG", "jpg")],
)
def test_accepts_supported_formats(fmt, extension):
    icon = custom_icons._validate_uploaded_icon(_image(fmt, (128, 128)))
    assert (icon.extension, icon.width, icon.height) == (extension, 128, 128)


def test_ico_uses_largest_square_entry():
    content = _image("ICO", (48, 48), sizes=[(16, 16), (32, 32), (48, 48)])
    icon = custom_icons._validate_uploaded_icon(content)
    assert (icon.extension, icon.width) == ("ico", 48)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not an image", "Upload a PNG"),
        (_image("PNG", (128, 64)), "square"),
        (_image("PNG", (32, 32)), "at least 64x64"),
        (_image("PNG", (2048, 2048)), "no larger than"),
    ],
)
def test_rejects_invalid_uploads(content, message):
    with pytest.raises(custom_icons.CustomIconError, match=message):
        custom_icons._validate_uploaded_icon(content)


def test_find_icons_reads_shipped_preset():
    preset_id = presets.load_preset_catalog()[0]["id"]
    icons = integration.find_icons(f"/p/{preset_id}/", presets.PRESETS_PATH / preset_id)
    assert icons["favicon"].startswith(f"/p/{preset_id}/favicon.ico?v=")
    assert icons["apple"].startswith(f"/p/{preset_id}/favicon-apple-180x180.png?v=")
    assert [item["sizes"] for item in icons["manifest"]] == ["192x192", "512x512"]
    assert {item["type"] for item in icons["manifest"]} == {"image/png"}


def test_preset_file_path_rejects_traversal():
    preset_id = presets.load_preset_catalog()[0]["id"]
    assert presets.get_preset_file_path(preset_id, "favicon.ico") is not None
    assert presets.get_preset_file_path("..", "manifest.json") is None
    assert presets.get_preset_file_path(preset_id, "../__init__.py") is None


def test_display_names():
    assert presets._display_name_from_id("poc-pride") == "POC Pride"
    assert presets._display_name_from_id("fire-orange") == "Fire Orange"


def _fake_hass(tmp_path: Path) -> SimpleNamespace:
    async def run(func, *args):
        return func(*args)

    return SimpleNamespace(
        data={},
        config=SimpleNamespace(path=lambda *parts: str(tmp_path.joinpath(*parts))),
        async_add_executor_job=run,
    )


def test_save_custom_icon_replaces_previous_upload(tmp_path):
    hass = _fake_hass(tmp_path)
    custom_icons.save_custom_icon(hass, _image("PNG", (128, 128)))
    slot = custom_icons.custom_icon_dir(hass)
    assert sorted(p.name for p in slot.iterdir()) == ["favicon-128x128.png", "favicon-apple-180x180.png"]

    ico = _image("ICO", (48, 48), sizes=[(16, 16), (48, 48)])
    custom_icons.save_custom_icon(hass, ico)
    assert sorted(p.name for p in slot.iterdir()) == ["favicon-48x48.ico", "favicon.ico"]
    assert [p.name for p in slot.parent.iterdir()] == [slot.name]  # no staging dir left
    assert custom_icons.get_custom_icon_preview_url(hass).startswith("/api/ha-favicon-changer/custom/favicon-48x48.ico?v=")


async def test_render_escapes_title_and_swaps_icons(tmp_path, monkeypatch):
    page = '<html><head><title>Home Assistant</title><link href="/static/icons/favicon.ico"></head></html>'
    monkeypatch.setattr(frontend.IndexView, "get_template", lambda self: SimpleNamespace(render=lambda: page))
    monkeypatch.setattr(frontend, "add_manifest_json_key", lambda key, value: None)
    preset_id = presets.load_preset_catalog()[0]["id"]
    title = '</script><img src=x onerror="alert(1)">'

    await integration._apply_config(_fake_hass(tmp_path), {"title": title, "icon_preset": preset_id})
    html = frontend.IndexView.get_template(None).render()  # type: ignore[arg-type]

    # Every "<" in the script string is \u003c, so neither "</script" nor "<!--" can break out.
    assert "<img" not in html
    assert 'const customTitle = "\\u003c/script>\\u003cimg src=x onerror=\\"alert(1)\\">";' in html
    assert "<title>&lt;/script&gt;&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</title>" in html
    assert html.count("</script>") == 1  # only the injected script's own closing tag
    assert "/static/icons/favicon.ico" not in html
    assert f"{PRESET_PUBLIC_ROOT}/{preset_id}/favicon.ico?v=" in html
