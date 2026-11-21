"""Conservative, training-only screen for the pinned Even HaEzer line set.

This is a candidate selector, not an audit or a pool admission. It combines the
histpurge crop-edge screen with exact normalised OCR agreement and a crop-border
ink check. OCR can miss marks or agree with an incorrect label, so every output
still requires an independent visual audit and the ordinary contamination gates.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cache
import hashlib
import json
from pathlib import Path
import unicodedata

from PIL import Image

RECORD = "cm_c03fe2f57871"
BOOK = "shulchan-arukh-eh-sefaria-commons"
MANIFEST_SHA = "9d9b67f31652f04f2228a1722a2014da42bff68a9f56d768e0be0f37bf08ca92"
FINAL = str.maketrans("ךםןףץ", "כמנפצ")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def letters(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text).lower() if c.isalnum()).translate(FINAL)


@dataclass(frozen=True)
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width


@cache
def page_words(path: Path) -> tuple[Word, ...]:
    with path.open(encoding="utf-8", newline="") as source:
        return tuple(Word(row["text"], *(int(row[key]) for key in ("left", "top", "width", "height")))
                     for row in csv.DictReader(source, delimiter="\t", quoting=csv.QUOTE_NONE)
                     if row["level"] == "5" and letters(row["text"] or ""))


def crop_words(words: tuple[Word, ...], bbox: list[int], crop: list[int]) -> list[Word]:
    _, top, _, height = bbox
    left, _, right, _ = crop
    inside = []
    for word in words:
        center = word.top + word.height / 2
        overlap_y = min(top + height, word.top + word.height) - max(top, word.top)
        overlap_x = min(right, word.right) - max(left, word.left)
        if top - 2 <= center <= top + height + 2 and overlap_y >= min(word.height, height) * 0.6 and overlap_x >= 2:
            inside.append(word)
    return sorted(inside, key=lambda word: -(word.left + word.right))


def screen(label: str, bbox: list[int], crop: list[int], page: tuple[Word, ...], image: Image.Image) -> list[str]:
    """Reject uncertain crops; no output is evidence that a crop is correct."""
    words = crop_words(page, bbox, crop)
    label_words = [w for w in label.split() if letters(w)]
    reasons = set()
    if not words or not label_words:
        reasons.add("missing_ocr_evidence")
    else:
        for truth, word in ((label_words[0], words[0]), (label_words[-1], words[-1])):
            expected, observed = letters(truth), letters(word.text)
            if SequenceMatcher(None, expected, observed, autojunk=False).ratio() < 0.66 or abs(len(expected) - len(observed)) > 1:
                reasons.add("crop_label_edge_mismatch")
            if crop[0] - word.left > 2 or word.right - crop[2] > 2:
                reasons.add("partial_ocr_word")
        # Exact agreement also catches some expansions without a recognized quote.
        # It cannot catch expansions when OCR itself silently expands the print.
        if [letters(w) for w in label_words] != [letters(w.text) for w in words]:
            reasons.add("ocr_label_disagreement")
    im = image.convert("L")
    width, height = im.size
    if width < 6 or height < 4:
        reasons.add("crop_too_small")
    else:
        if any(im.getpixel((x, y)) < 100 for x in (*range(3), *range(width - 3, width)) for y in range(height)):
            reasons.add("side_border_ink")
        if any(sum(im.getpixel((x, y)) < 100 for x in range(width)) >= 20 for y in (0, 1, height - 2, height - 1)):
            reasons.add("vertical_border_ink")
    return sorted(reasons)


def run(manifest: Path, crops: Path, ocr: Path) -> dict:
    payload = manifest.read_bytes()
    if digest(payload) != MANIFEST_SHA:
        raise ValueError("Unexpected source manifest hash")
    rows = [json.loads(line) for line in payload.splitlines()]
    rows = [r for r in rows if r.get("record_id") == RECORD]
    if len(rows) != 1056 or len({r['id'] for r in rows}) != len(rows):
        raise ValueError("Unexpected EH roster")
    accepted, rejected, ocr_hashes = [], {}, {}
    for row in rows:
        name = row["id"]
        if (row["split"], row["book"], row["script"], row["text_licence"], row["image"], row["page_ocr"]) != (
            "train", BOOK, "square", "Public Domain", f"train/{RECORD}/{name}.png", "ocr"
        ):
            raise ValueError(f"Unexpected provenance for {name}")
        crop_path = crops / (name + ".png")
        data = crop_path.read_bytes()
        if digest(data) != row["image_sha256"]:
            raise ValueError(f"Crop hash mismatch: {name}")
        ocr_path = ocr / f"c{row['canvas_index']:04d}.tsv"
        ocr_hashes[ocr_path.name] = digest(ocr_path.read_bytes())
        page = page_words(ocr_path)
        with Image.open(crop_path) as image:
            reasons = screen(row["text"], row["bbox_image"], row["crop_box_image"], page, image)
        if reasons:
            rejected[name] = reasons
        else:
            accepted.append({"id": name, "image_sha256": row["image_sha256"],
                             "label_sha256": digest(row["text"].encode())})
    return {"schema": "heocr.phist.eh-conservative-screen.v1", "source_manifest_sha256": MANIFEST_SHA,
            "ocr_sha256": dict(sorted(ocr_hashes.items())),
            "accepted": sorted(accepted, key=lambda row: row["id"]), "rejected": rejected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--crops", type=Path, required=True, help="flat directory of original EH PNGs")
    parser.add_argument("--ocr", type=Path, required=True, help="EH page TSV directory")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.manifest, args.crops, args.ocr)
    with args.out.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, ensure_ascii=False)
        out.write("\n")


if __name__ == "__main__":
    main()
