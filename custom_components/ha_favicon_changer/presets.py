"""Helpers for shipped favicon presets."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypedDict

_LOGGER = logging.getLogger(__name__)

PRESETS_PATH = Path(__file__).resolve().parent / "presets"

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


def _display_name_from_id(preset_id: str) -> str:
    return " ".join(
        "POC" if word.upper() == "POC" else word.capitalize()
        for word in preset_id.split("-")
        if word
    ) or preset_id


def load_preset_catalog() -> tuple[PresetInfo, ...]:
    """Discover preset metadata from the shipped preset folders."""
    if not PRESETS_PATH.is_dir():
        _LOGGER.warning("Preset root does not exist: %s", PRESETS_PATH)
        return ()

    catalog: list[PresetInfo] = []
    for preset_dir in PRESETS_PATH.iterdir():
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


def get_preset_file_path(preset_id: str, filename: str) -> Path | None:
    """Return the on-disk file path for a preset asset."""
    if Path(preset_id).name != preset_id or Path(filename).name != filename:
        return None
    if preset_id not in {preset["id"] for preset in load_preset_catalog()}:
        return None

    file_path = PRESETS_PATH / preset_id / filename
    return file_path if file_path.is_file() else None
