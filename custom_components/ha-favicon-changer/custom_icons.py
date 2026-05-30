"""Helpers for custom uploaded favicon assets."""

from __future__ import annotations

import logging
import re
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import (
    CUSTOM_ICON_PUBLIC_ROOT,
    CUSTOM_ICON_SLOT,
    CUSTOM_ICON_STORAGE_ROOT,
    MAX_UPLOAD_BYTES,
)

_LOGGER = logging.getLogger(__name__)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_ICO_HEADER = b"\x00\x00\x01\x00"
_SUPPORTED_CONTENT_TYPES = {
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/pjpeg": "jpg",
    "image/png": "png",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
    "image/webp": "webp",
}
_SUPPORTED_EXTENSIONS = {
    ".gif": "gif",
    ".jpeg": "jpg",
    ".jpg": "jpg",
    ".png": "png",
    ".ico": "ico",
    ".webp": "webp",
}
_MIN_PNG_SIZE = 64
_MIN_ICO_SIZE = 16
_MAX_ICON_SIZE = 1024
_SIZED_ICON_RE = re.compile(
    r"^favicon-(\d+)x\1\.(png|ico|webp|gif|jpe?g)$", re.IGNORECASE
)
_JPEG_SOF_MARKERS = frozenset(
    {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
)


class CustomIconError(ValueError):
    """Raised when an uploaded icon is invalid."""


@dataclass(frozen=True, slots=True)
class UploadedIcon:
    """Validated uploaded icon metadata."""

    extension: str
    width: int
    height: int


def _custom_icon_root(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(*CUSTOM_ICON_STORAGE_ROOT))


def _custom_icon_slot_dir(hass: HomeAssistant) -> Path:
    return _custom_icon_root(hass) / CUSTOM_ICON_SLOT


def get_custom_icon_public_path() -> str:
    """Return the public directory path for the active custom icon."""
    return f"{CUSTOM_ICON_PUBLIC_ROOT}/{CUSTOM_ICON_SLOT}/"


def get_custom_icon_file_path(
    hass: HomeAssistant, slot: str, filename: str
) -> Path | None:
    """Return the custom icon file path for a public asset request."""
    if slot != CUSTOM_ICON_SLOT or Path(filename).name != filename:
        return None

    file_path = _custom_icon_slot_dir(hass) / filename
    if not file_path.is_file():
        return None
    return file_path


def get_custom_icon_preview_url(hass: HomeAssistant) -> str | None:
    """Return a cache-busted URL for the best custom icon preview."""
    slot_dir = _custom_icon_slot_dir(hass)
    sized_candidates: list[tuple[int, Path]] = []
    slot_entries = slot_dir.iterdir() if slot_dir.is_dir() else ()
    for candidate in slot_entries:
        if not candidate.is_file():
            continue
        match = _SIZED_ICON_RE.match(candidate.name)
        if match:
            sized_candidates.append((int(match.group(1)), candidate))

    candidates = [
        candidate
        for _, candidate in sorted(
            sized_candidates, key=lambda item: item[0], reverse=True
        )
    ]
    apple_icon = slot_dir / "favicon-apple-180x180.png"
    if apple_icon.is_file():
        candidates.append(apple_icon)
    favicon = slot_dir / "favicon.ico"
    if favicon.is_file():
        candidates.append(favicon)

    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            version = candidate.stat().st_mtime_ns
        except OSError:
            version = None
        url = f"{get_custom_icon_public_path()}{candidate.name}"
        if version is not None:
            url = f"{url}?v={version}"
        return url

    return None


def _detect_png(content: bytes) -> UploadedIcon | None:
    if not content.startswith(_PNG_SIGNATURE):
        return None
    if len(content) < 24:
        raise CustomIconError("PNG file is incomplete.")

    width, height = struct.unpack(">II", content[16:24])
    return UploadedIcon("png", width, height)


def _detect_ico(content: bytes) -> UploadedIcon | None:
    if not content.startswith(_ICO_HEADER):
        return None
    if len(content) < 6:
        raise CustomIconError("ICO file is incomplete.")

    count = struct.unpack("<H", content[4:6])[0]
    if count <= 0 or count > 64:
        raise CustomIconError("ICO file has an invalid image count.")

    entries: list[tuple[int, int]] = []
    offset = 6
    for _ in range(count):
        if len(content) < offset + 16:
            raise CustomIconError("ICO directory is incomplete.")
        width = content[offset] or 256
        height = content[offset + 1] or 256
        entries.append((width, height))
        offset += 16

    square_entries = [(width, height) for width, height in entries if width == height]
    if not square_entries:
        raise CustomIconError("ICO file must contain at least one square icon.")

    width, height = max(square_entries, key=lambda item: item[0])
    return UploadedIcon("ico", width, height)


def _detect_webp(content: bytes) -> UploadedIcon | None:
    if len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        return None

    offset = 12
    while offset + 8 <= len(content):
        chunk_type = content[offset : offset + 4]
        chunk_size = struct.unpack("<I", content[offset + 4 : offset + 8])[0]
        payload_offset = offset + 8
        payload_end = payload_offset + chunk_size
        if payload_end > len(content):
            raise CustomIconError("WebP file is incomplete.")

        payload = content[payload_offset:payload_end]
        if chunk_type == b"VP8X":
            if chunk_size < 10:
                raise CustomIconError("WebP file is incomplete.")
            width = int.from_bytes(payload[4:7], "little") + 1
            height = int.from_bytes(payload[7:10], "little") + 1
            return UploadedIcon("webp", width, height)

        if chunk_type == b"VP8L":
            if chunk_size < 5 or payload[0] != 0x2F:
                raise CustomIconError("WebP lossless header is invalid.")
            width = 1 + (payload[1] | ((payload[2] & 0x3F) << 8))
            height = 1 + (
                ((payload[2] & 0xC0) >> 6)
                | (payload[3] << 2)
                | ((payload[4] & 0x0F) << 10)
            )
            return UploadedIcon("webp", width, height)

        if chunk_type == b"VP8 ":
            if chunk_size < 10 or payload[3:6] != b"\x9d\x01\x2a":
                raise CustomIconError("WebP lossy header is invalid.")
            width = struct.unpack("<H", payload[6:8])[0] & 0x3FFF
            height = struct.unpack("<H", payload[8:10])[0] & 0x3FFF
            return UploadedIcon("webp", width, height)

        offset = payload_end + (chunk_size % 2)

    raise CustomIconError("WebP file does not include readable dimensions.")


def _detect_gif(content: bytes) -> UploadedIcon | None:
    if not (content.startswith(b"GIF87a") or content.startswith(b"GIF89a")):
        return None
    if len(content) < 10:
        raise CustomIconError("GIF file is incomplete.")

    width, height = struct.unpack("<HH", content[6:10])
    return UploadedIcon("gif", width, height)


def _detect_jpeg(content: bytes) -> UploadedIcon | None:
    if not content.startswith(b"\xff\xd8"):
        return None

    offset = 2
    while offset < len(content):
        while offset < len(content) and content[offset] == 0xFF:
            offset += 1
        if offset >= len(content):
            break

        marker = content[offset]
        offset += 1
        if marker in (0x00, 0x01, 0xD8, 0xD9):
            continue
        if marker == 0xDA:
            break
        if offset + 2 > len(content):
            raise CustomIconError("JPEG file is incomplete.")

        segment_length = struct.unpack(">H", content[offset : offset + 2])[0]
        if segment_length < 2:
            raise CustomIconError("JPEG file has an invalid segment.")
        segment_end = offset + segment_length
        if segment_end > len(content):
            raise CustomIconError("JPEG file is incomplete.")

        if marker in _JPEG_SOF_MARKERS:
            if segment_length < 7:
                raise CustomIconError("JPEG size segment is invalid.")
            height = struct.unpack(">H", content[offset + 3 : offset + 5])[0]
            width = struct.unpack(">H", content[offset + 5 : offset + 7])[0]
            return UploadedIcon("jpg", width, height)

        offset = segment_end

    raise CustomIconError("JPEG file does not include readable dimensions.")


def _validate_uploaded_icon(
    filename: str | None, content_type: str | None, content: bytes
) -> UploadedIcon:
    if not content:
        raise CustomIconError("Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise CustomIconError("Icon is larger than 1 MiB.")

    suffix = Path(filename or "").suffix.lower()
    extension_hint = _SUPPORTED_EXTENSIONS.get(suffix)
    content_type_hint = _SUPPORTED_CONTENT_TYPES.get((content_type or "").lower())

    icon = (
        _detect_png(content)
        or _detect_ico(content)
        or _detect_webp(content)
        or _detect_gif(content)
        or _detect_jpeg(content)
    )
    if icon is None:
        raise CustomIconError("Upload a PNG, ICO, WebP, GIF, or JPEG icon.")

    if extension_hint and extension_hint != icon.extension:
        raise CustomIconError("File extension does not match the icon data.")
    if content_type_hint and content_type_hint != icon.extension:
        raise CustomIconError("Content type does not match the icon data.")

    min_size = _MIN_ICO_SIZE if icon.extension == "ico" else _MIN_PNG_SIZE
    if icon.width != icon.height:
        raise CustomIconError("Icon must be square.")
    if icon.width < min_size:
        raise CustomIconError(f"Icon must be at least {min_size}x{min_size}.")
    if icon.width > _MAX_ICON_SIZE:
        raise CustomIconError(
            f"Icon must be no larger than {_MAX_ICON_SIZE}x{_MAX_ICON_SIZE}."
        )

    return icon


def save_custom_icon(
    hass: HomeAssistant, filename: str | None, content_type: str | None, content: bytes
) -> str:
    """Validate and save an uploaded icon, returning its public path."""
    icon = _validate_uploaded_icon(filename, content_type, content)
    destination_dir = _custom_icon_slot_dir(hass)
    staging_dir: Path | None = _custom_icon_root(hass) / f".{CUSTOM_ICON_SLOT}-staging"

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
