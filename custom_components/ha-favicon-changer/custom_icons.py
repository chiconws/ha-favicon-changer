"""Helpers for custom uploaded favicon assets."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from homeassistant.core import HomeAssistant
from PIL import Image

from .const import (
    CUSTOM_ICON_PUBLIC_ROOT,
    CUSTOM_ICON_SLOT,
    CUSTOM_ICON_STORAGE_ROOT,
    MAX_UPLOAD_BYTES,
)

_LOGGER = logging.getLogger(__name__)

# Pillow format name -> saved file extension.
_FORMAT_EXTENSIONS = {
    "GIF": "gif",
    "ICO": "ico",
    "JPEG": "jpg",
    "PNG": "png",
    "WEBP": "webp",
}
SUPPORTED_CONTENT_TYPES = {
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/pjpeg": "jpg",
    "image/png": "png",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
    "image/webp": "webp",
}
SUPPORTED_EXTENSIONS = {
    ".gif": "gif",
    ".jpeg": "jpg",
    ".jpg": "jpg",
    ".png": "png",
    ".ico": "ico",
    ".webp": "webp",
}
MIN_ICO_SIZE = 16
MIN_ICON_SIZE = 64
MAX_ICON_SIZE = 1024
_SIZED_ICON_RE = re.compile(
    r"^favicon-(\d+)x\1\.(png|ico|webp|gif|jpe?g)$", re.IGNORECASE
)


class CustomIconError(ValueError):
    """Raised when an uploaded icon is invalid."""


@dataclass(frozen=True, slots=True)
class UploadedIcon:
    """Validated uploaded icon metadata."""

    extension: str
    width: int
    height: int


def custom_icon_dir(hass: HomeAssistant) -> Path:
    """Return the directory holding the active custom icon files."""
    return Path(hass.config.path(*CUSTOM_ICON_STORAGE_ROOT, CUSTOM_ICON_SLOT))


def get_custom_icon_public_path() -> str:
    """Return the public directory path for the active custom icon."""
    return f"{CUSTOM_ICON_PUBLIC_ROOT}/{CUSTOM_ICON_SLOT}/"


def get_custom_icon_file_path(
    hass: HomeAssistant, slot: str, filename: str
) -> Path | None:
    """Return the custom icon file path for a public asset request."""
    if slot != CUSTOM_ICON_SLOT or Path(filename).name != filename:
        return None

    file_path = custom_icon_dir(hass) / filename
    if not file_path.is_file():
        return None
    return file_path


def get_custom_icon_preview_url(hass: HomeAssistant) -> str | None:
    """Return a cache-busted URL for the best custom icon preview."""
    slot_dir = custom_icon_dir(hass)
    if not slot_dir.is_dir():
        return None

    sized = [
        (int(match.group(1)), entry)
        for entry in slot_dir.iterdir()
        if entry.is_file() and (match := _SIZED_ICON_RE.match(entry.name))
    ]
    candidates = [entry for _, entry in sorted(sized, key=lambda item: item[0], reverse=True)]
    candidates += [slot_dir / "favicon-apple-180x180.png", slot_dir / "favicon.ico"]

    for candidate in candidates:
        try:
            version = candidate.stat().st_mtime_ns
        except OSError:
            continue
        return f"{get_custom_icon_public_path()}{candidate.name}?v={version}"

    return None


def _identify_icon(content: bytes) -> UploadedIcon:
    try:
        with Image.open(BytesIO(content), formats=list(_FORMAT_EXTENSIONS)) as image:
            extension = _FORMAT_EXTENSIONS[image.format]
            if extension != "ico":
                return UploadedIcon(extension, *image.size)
            square = [size for size in image.info.get("sizes", ()) if size[0] == size[1]]
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as err:
        raise CustomIconError("Upload a PNG, ICO, WebP, GIF, or JPEG icon.") from err

    if not square:
        raise CustomIconError("ICO file must contain at least one square icon.")
    return UploadedIcon("ico", *max(square))


def _validate_uploaded_icon(
    filename: str | None, content_type: str | None, content: bytes
) -> UploadedIcon:
    if not content:
        raise CustomIconError("Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise CustomIconError("Icon is larger than 1 MiB.")

    suffix = Path(filename or "").suffix.lower()
    extension_hint = SUPPORTED_EXTENSIONS.get(suffix)
    content_type_hint = SUPPORTED_CONTENT_TYPES.get((content_type or "").lower())

    icon = _identify_icon(content)

    if extension_hint and extension_hint != icon.extension:
        raise CustomIconError("File extension does not match the icon data.")
    if content_type_hint and content_type_hint != icon.extension:
        raise CustomIconError("Content type does not match the icon data.")

    min_size = MIN_ICO_SIZE if icon.extension == "ico" else MIN_ICON_SIZE
    if icon.width != icon.height:
        raise CustomIconError("Icon must be square.")
    if icon.width < min_size:
        raise CustomIconError(f"Icon must be at least {min_size}x{min_size}.")
    if icon.width > MAX_ICON_SIZE:
        raise CustomIconError(
            f"Icon must be no larger than {MAX_ICON_SIZE}x{MAX_ICON_SIZE}."
        )

    return icon


def save_custom_icon(
    hass: HomeAssistant, filename: str | None, content_type: str | None, content: bytes
) -> str:
    """Validate and save an uploaded icon, returning its public path."""
    icon = _validate_uploaded_icon(filename, content_type, content)
    destination_dir = custom_icon_dir(hass)
    staging_dir: Path | None = destination_dir.with_name(f".{CUSTOM_ICON_SLOT}-staging")

    try:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)

        if icon.extension == "ico":
            filenames = ["favicon.ico", f"favicon-{icon.width}x{icon.height}.ico"]
        elif icon.extension in {"gif", "jpg", "webp"}:
            filenames = [f"favicon-{icon.width}x{icon.height}.{icon.extension}"]
        else:
            filenames = [
                f"favicon-{icon.width}x{icon.height}.png",
                "favicon-apple-180x180.png",
            ]

        for output_name in filenames:
            (staging_dir / output_name).write_bytes(content)

        if destination_dir.exists():
            shutil.rmtree(destination_dir)
        staging_dir.rename(destination_dir)
        staging_dir = None
    except OSError as err:
        raise CustomIconError(f"Could not save icon: {err}") from err
    finally:
        if staging_dir is not None and staging_dir.exists():
            try:
                shutil.rmtree(staging_dir)
            except OSError:
                _LOGGER.exception("Failed to remove custom icon staging directory")

    _LOGGER.info(
        "Saved custom %s icon (%dx%d) to %s",
        icon.extension,
        icon.width,
        icon.height,
        destination_dir,
    )
    return get_custom_icon_public_path()
