from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from defusedxml import ElementTree as DefusedET

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
    root = DefusedET.fromstring(path.read_text(encoding="utf-8"))
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
    sof_markers = {
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
    with path.open("rb") as handle:
        if handle.read(2) != b"\xff\xd8":
            raise ValueError("invalid jpeg header")
        while True:
            byte = handle.read(1)
            if not byte:
                break
            if byte != b"\xff":
                continue

            while True:
                marker_byte = handle.read(1)
                if not marker_byte:
                    raise ValueError("truncated jpeg while reading marker")
                if marker_byte != b"\xff":
                    break

            marker = marker_byte[0]
            if marker in {0xD8, 0xD9}:
                continue

            length_bytes = handle.read(2)
            if len(length_bytes) != 2:
                raise ValueError("truncated jpeg while reading segment length")
            segment_length = struct.unpack(">H", length_bytes)[0]
            if segment_length < 2:
                raise ValueError("invalid jpeg segment length")

            if marker in sof_markers:
                segment_data = handle.read(segment_length - 2)
                if len(segment_data) != segment_length - 2:
                    raise ValueError("truncated jpeg while reading SOF segment")
                if len(segment_data) < 5:
                    raise ValueError("invalid SOF segment length")
                height, width = struct.unpack(">HH", segment_data[1:5])
                return width, height

            to_skip = segment_length - 2
            if handle.seekable():
                handle.seek(to_skip, 1)
            else:
                skipped = handle.read(to_skip)
                if len(skipped) != to_skip:
                    raise ValueError("truncated jpeg while skipping segment")
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
