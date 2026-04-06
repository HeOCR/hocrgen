from __future__ import annotations

from pathlib import Path

from hocrgen.utils.io import copy_file


FORMAT_EXTENSIONS = {
    "svg": ".svg",
    "png": ".png",
    "jpeg": ".jpg",
}


def sanitize_item_id(item_id: str) -> str:
    return item_id.replace(":", "__").replace("/", "_")


def normalized_asset_destination(root: Path, item_id: str, asset_index: int, asset_format: str) -> Path:
    extension = FORMAT_EXTENSIONS[asset_format]
    return root / sanitize_item_id(item_id) / f"asset_{asset_index:02d}{extension}"


def preview_destination(root: Path, item_id: str, asset_index: int, asset_format: str) -> Path:
    extension = FORMAT_EXTENSIONS[asset_format]
    return root / sanitize_item_id(item_id) / f"asset_{asset_index:02d}{extension}"


def copy_asset(source: Path, destination: Path) -> Path:
    return copy_file(source, destination)
