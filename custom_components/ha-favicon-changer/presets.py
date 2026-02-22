"""Helpers for shipped favicon presets."""

from __future__ import annotations

import filecmp
import logging
import shutil
from pathlib import Path
from typing import TypedDict

from homeassistant.core import HomeAssistant

from .const import PRESET_PUBLIC_ROOT, PRESET_STORAGE_ROOT

_LOGGER = logging.getLogger(__name__)

_MODULE_PATH = Path(__file__).resolve().parent
_PRESETS_PATH = _MODULE_PATH / "presets"
_MANAGED_MARKER_FILES = (
    ".ha-favicon-changer-managed",
    ".hass-favicon-managed",
)

_REQUIRED_PRESET_FILES = frozenset(
    {
        "favicon.ico",
        "favicon-apple-180x180.png",
        "favicon-192x192.png",
        "favicon-512x512.png",
    }
)


class PresetInfo(TypedDict):
    """A discovered preset descriptor."""

    id: str
    name: str


def _is_managed_preset_dir(directory: Path, known_preset_ids: set[str]) -> bool:
    return directory.name in known_preset_ids or any(
        (directory / marker).exists() for marker in _MANAGED_MARKER_FILES
    )


def _prune_preset_storage(
    destination_root: Path, known_preset_ids: set[str], keep: set[str] | None = None
) -> int:
    """Remove cached preset folders except those in keep."""
    if not destination_root.exists():
        return 0

    keep = keep or set()
    removed = 0
    for entry in destination_root.iterdir():
        if not entry.is_dir() or entry.name in keep:
            continue
        if not _is_managed_preset_dir(entry, known_preset_ids):
            continue
        try:
            shutil.rmtree(entry)
            removed += 1
        except OSError:
            _LOGGER.exception("Failed to remove old preset directory: %s", entry)
    return removed


def _display_name_from_id(preset_id: str) -> str:
    words = preset_id.split("-")
    output: list[str] = []
    for word in words:
        if not word:
            continue
        if word.upper() == "POC":
            output.append("POC")
            continue
        output.append(word.capitalize())
    return " ".join(output) or preset_id


def load_preset_catalog() -> tuple[PresetInfo, ...]:
    """Discover preset metadata from the shipped preset folders."""
    if not _PRESETS_PATH.is_dir():
        _LOGGER.warning("Preset root does not exist: %s", _PRESETS_PATH)
        return ()

    catalog: list[PresetInfo] = []
    for preset_dir in sorted(_PRESETS_PATH.iterdir(), key=lambda path: path.name.lower()):
        if not preset_dir.is_dir():
            continue

        files = {entry.name for entry in preset_dir.iterdir() if entry.is_file()}
        if not _REQUIRED_PRESET_FILES.issubset(files):
            missing = sorted(_REQUIRED_PRESET_FILES - files)
            _LOGGER.debug(
                "Skipping preset '%s'; missing files: %s",
                preset_dir.name,
                ", ".join(missing),
            )
            continue

        catalog.append(
            PresetInfo(
                id=preset_dir.name,
                name=_display_name_from_id(preset_dir.name),
            )
        )

    catalog.sort(key=lambda item: item["name"].lower())
    return tuple(catalog)


def get_preset_ids(catalog: tuple[PresetInfo, ...] | None = None) -> set[str]:
    """Return all valid preset IDs."""
    if catalog is None:
        catalog = load_preset_catalog()
    return {preset["id"] for preset in catalog}


def resolve_preset_icon_path(hass: HomeAssistant, preset_id: str) -> str | None:
    """Copy a preset into /www and return its /local path."""
    source_dir = _PRESETS_PATH / preset_id
    if not source_dir.is_dir():
        _LOGGER.warning("Preset directory does not exist: %s", source_dir)
        return None

    destination_root = Path(hass.config.path(*PRESET_STORAGE_ROOT))
    try:
        destination_root.mkdir(parents=True, exist_ok=True)
    except OSError:
        _LOGGER.exception(
            "Failed to create preset root destination directory: %s", destination_root
        )
        return None

    known_preset_ids = get_preset_ids()
    removed = _prune_preset_storage(
        destination_root, known_preset_ids=known_preset_ids, keep={preset_id}
    )
    if removed:
        _LOGGER.debug(
            "Removed %d cached preset folder(s) from %s before syncing '%s'",
            removed,
            destination_root,
            preset_id,
        )

    destination_dir = destination_root / preset_id
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        _LOGGER.exception("Failed to create preset destination directory: %s", destination_dir)
        return None

    marker_file = destination_dir / _MANAGED_MARKER_FILES[0]
    try:
        marker_file.touch(exist_ok=True)
    except OSError:
        _LOGGER.exception("Failed to create managed marker file: %s", marker_file)
        return None

    copied_files = 0
    for source_file in source_dir.iterdir():
        if not source_file.is_file():
            continue

        destination_file = destination_dir / source_file.name
        if destination_file.exists() and filecmp.cmp(source_file, destination_file, shallow=False):
            continue
        try:
            shutil.copy2(source_file, destination_file)
            copied_files += 1
        except OSError:
            _LOGGER.exception(
                "Failed to copy preset file '%s' to '%s'", source_file, destination_file
            )
            return None

    _LOGGER.debug(
        "Preset '%s' synchronized to '%s' (copied_files=%d)",
        preset_id,
        destination_dir,
        copied_files,
    )

    return f"{PRESET_PUBLIC_ROOT}/{preset_id}/"


def cleanup_preset_storage(hass: HomeAssistant) -> int:
    """Remove all cached preset folders from /www/favicon-presets."""
    destination_root = Path(hass.config.path(*PRESET_STORAGE_ROOT))
    known_preset_ids = get_preset_ids()
    removed = _prune_preset_storage(destination_root, known_preset_ids=known_preset_ids)
    if removed:
        _LOGGER.debug(
            "Removed %d cached preset folder(s) from %s",
            removed,
            destination_root,
        )
    return removed
