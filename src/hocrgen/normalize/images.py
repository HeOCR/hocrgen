from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from hocrgen.utils.hashing import sha256_file


@dataclass(frozen=True)
class AssetTechnicalMetadata:
    asset_format: str
    media_type: str
    width: int | None
    height: int | None
    file_size_bytes: int
    sha256: str
    is_vector: bool


def _parse_svg_dimension(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip().lower().removesuffix("px")
    try:
        return int(round(float(stripped)))
    except ValueError:
        return None


def _parse_svg(path: Path) -> tuple[int | None, int | None]:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    width = _parse_svg_dimension(root.attrib.get("width"))
    height = _parse_svg_dimension(root.attrib.get("height"))
    if width is not None and height is not None:
        return width, height
    view_box = root.attrib.get("viewBox")
    if view_box:
        parts = view_box.replace(",", " ").split()
        if len(parts) == 4:
            try:
                return int(round(float(parts[2]))), int(round(float(parts[3])))
            except ValueError:
                return width, height
    return width, height


def _parse_png_dimensions(header: bytes) -> tuple[int, int]:
    if len(header) < 24:
        raise ValueError("png header too short")
    return struct.unpack(">II", header[16:24])


def _parse_jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("invalid jpeg header")
    offset = 2
    while offset < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            break
        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if offset + 7 > len(data):
                break
            height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
            return width, height
        offset += segment_length
    raise ValueError("jpeg dimensions not found")


def detect_asset_metadata(path: Path) -> AssetTechnicalMetadata:
    file_size_bytes = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(512)
    suffix = path.suffix.lower()
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height = _parse_png_dimensions(header)
        return AssetTechnicalMetadata(
            asset_format="png",
            media_type="image/png",
            width=width,
            height=height,
            file_size_bytes=file_size_bytes,
            sha256=sha256_file(path),
            is_vector=False,
        )
    if header.startswith(b"\xff\xd8"):
        width, height = _parse_jpeg_dimensions(path)
        return AssetTechnicalMetadata(
            asset_format="jpeg",
            media_type="image/jpeg",
            width=width,
            height=height,
            file_size_bytes=file_size_bytes,
            sha256=sha256_file(path),
            is_vector=False,
        )
    if suffix == ".svg" or b"<svg" in header.lower():
        width, height = _parse_svg(path)
        return AssetTechnicalMetadata(
            asset_format="svg",
            media_type="image/svg+xml",
            width=width,
            height=height,
            file_size_bytes=file_size_bytes,
            sha256=sha256_file(path),
            is_vector=True,
        )
    raise ValueError(f"unsupported asset format: {path}")
