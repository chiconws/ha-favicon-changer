"""Edge cases: icon discovery, upload validation, storage paths and the preset catalog."""

import importlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

integration = importlib.import_module("custom_components.favicon_changer")
custom_icons = importlib.import_module("custom_components.favicon_changer.custom_icons")
presets = importlib.import_module("custom_components.favicon_changer.preset_catalog")


def _png(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size).save(buffer, "PNG")
    return buffer.getvalue()


def _hass(tmp_path: Path):
    return SimpleNamespace(config=SimpleNamespace(path=lambda *parts: str(tmp_path.joinpath(*parts))))


def test_find_icons_unreadable_dir(tmp_path, caplog) -> None:
    assert integration.find_icons("/x/", tmp_path / "missing") == {}
    assert "Could not read icon directory" in caplog.text


def test_find_icons_skips_junk_and_falls_back_to_manifest(tmp_path, caplog) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "favicon-64x64.unknownext").write_bytes(b"x")
    (tmp_path / "favicon-192x192.png").write_bytes(b"x")
    (tmp_path / "favicon-32x32.png").write_bytes(b"x")
    icons = integration.find_icons("/x/", tmp_path)
    assert [m["sizes"] for m in icons["manifest"]] == ["32x32", "192x192"]
    assert icons["favicon"].startswith("/x/favicon-32x32.png")


def test_find_icons_empty_dir_warns(tmp_path, caplog) -> None:
    assert integration.find_icons("/x/", tmp_path) == {}
    assert "No supported icon files" in caplog.text


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "empty"),
        (b"x" * (1024 * 1024 + 1), "larger than 1 MiB"),
        (b"not an image", "Upload a PNG"),
        (_png((128, 64)), "must be square"),
        (_png((32, 32)), "at least 64x64"),
        (_png((2048, 2048)), "no larger than 1024x1024"),
    ],
)
def test_upload_rejected(content, message) -> None:
    with pytest.raises(custom_icons.CustomIconError, match=message):
        custom_icons._validate_uploaded_icon(content)


def test_ico_without_square_entry_is_rejected() -> None:
    buffer = io.BytesIO()
    Image.new("RGBA", (64, 32)).save(buffer, "ICO", sizes=[(64, 32)])
    with pytest.raises(custom_icons.CustomIconError, match="square"):
        custom_icons._validate_uploaded_icon(buffer.getvalue())


def test_custom_icon_paths(tmp_path) -> None:
    hass = _hass(tmp_path)
    assert custom_icons.get_custom_icon_preview_url(hass) is None
    assert custom_icons.get_custom_icon_file_path(hass, "../secret") is None
    assert custom_icons.get_custom_icon_file_path(hass, "favicon.ico") is None
    custom_icons.save_custom_icon(hass, _png((64, 64)))
    assert custom_icons.get_custom_icon_file_path(hass, "favicon-64x64.png") is not None


def test_save_failure_is_reported(tmp_path, monkeypatch) -> None:
    hass = _hass(tmp_path)
    monkeypatch.setattr(Path, "rename", lambda self, target: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(custom_icons.CustomIconError, match="disk full"):
        custom_icons.save_custom_icon(hass, _png((64, 64)))
    assert not any(p.name.endswith("-staging") for p in custom_icons.custom_icon_dir(hass).parent.iterdir())


def test_preset_catalog_edges(tmp_path, monkeypatch) -> None:
    (tmp_path / "incomplete").mkdir()
    (tmp_path / "loose-file").write_bytes(b"")
    monkeypatch.setattr(presets, "PRESETS_PATH", tmp_path)
    assert presets.load_preset_catalog() == ()


@pytest.mark.parametrize(
    ("fmt", "kwargs", "expected"),
    [
        ("ICO", {"sizes": [(48, 48)]}, {"favicon.ico", "favicon-48x48.ico"}),
        ("GIF", {}, {"favicon-64x64.gif"}),
    ],
)
def test_save_and_preview(tmp_path, fmt, kwargs, expected) -> None:
    hass = _hass(tmp_path)
    buffer = io.BytesIO()
    Image.new("RGBA" if fmt == "ICO" else "RGB", (64, 64) if fmt != "ICO" else (48, 48)).save(buffer, fmt, **kwargs)
    custom_icons.save_custom_icon(hass, buffer.getvalue())
    assert {p.name for p in custom_icons.custom_icon_dir(hass).iterdir()} == expected
    preview = custom_icons.get_custom_icon_preview_url(hass)
    assert preview and preview.split("?")[0].rsplit("/", 1)[1] in expected


async def test_diagnostics(hass, entry) -> None:
    diagnostics = importlib.import_module("custom_components.favicon_changer.diagnostics")
    diag = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    assert diag["config"]["title"] == "My Home" and diag["custom_icon"] is None
