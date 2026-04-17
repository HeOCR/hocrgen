from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from hocrgen.config.loader import load_yaml_file
from hocrgen.utils.hashing import sha256_file


GENERATOR_VERSION = "b3b-jpeg-v1"
CANVAS_SIZE = (1200, 1600)
PAPER_MARGIN = 96

PRINTED_TITLES = [
    "מכתב מנהלי",
    "דו\"ח קבלה",
    "רישום ארכיוני",
]

HANDWRITTEN_TITLES = [
    "פנקס הערות",
    "רישום קצר",
    "הודעה פנימית",
]

FOOTER_LABELS = [
    "סימן",
    "רישום",
    "עמוד",
]


@dataclass(frozen=True)
class SyntheticDocument:
    title: str
    body: str
    footer: str
    template_id: str
    font_id: str
    path: Path
    sha256: str
    generator_version: str


def load_font_manifest(path: Path) -> dict:
    return load_yaml_file(path)


def load_text_corpus(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _font_path(manifest_path: Path, font_entry: dict) -> Path:
    file_name = str(font_entry.get("file", "")).strip()
    if not file_name:
        raise ValueError(f"Synthetic font entry is missing a file reference: {font_entry.get('id', '<unknown>')}")
    path = (manifest_path.parent / file_name).resolve()
    if not path.exists():
        raise ValueError(f"Synthetic font file is missing: {path}")
    return path


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path), size)


def _wrap_hebrew_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        left, _top, right, _bottom = draw.textbbox((0, 0), candidate, font=font)
        width = right - left
        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _paper_background(randomizer: random.Random, size: tuple[int, int], tone: str) -> Image.Image:
    if tone == "printed":
        base = (246, 241, 230)
    else:
        base = (243, 235, 220)
    image = Image.new("RGB", size, base)
    noise = Image.frombytes("L", size, randomizer.randbytes(size[0] * size[1]))
    noise = noise.point(lambda value: int(128 + ((value - 128) * 0.08)))
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    textured = ImageChops.add(image, noise_rgb, scale=1.0, offset=-128)
    return Image.blend(image, textured, alpha=0.05)


def _apply_grain(image: Image.Image, randomizer: random.Random) -> Image.Image:
    noise = Image.frombytes("L", image.size, randomizer.randbytes(image.size[0] * image.size[1]))
    noise = noise.point(lambda value: int(96 + ((value - 128) * 0.22)))
    textured = ImageChops.add_modulo(image.convert("RGB"), Image.merge("RGB", (noise, noise, noise)))
    return Image.blend(image, textured, alpha=0.08)


def _degrade(image: Image.Image, randomizer: random.Random, background: tuple[int, int, int]) -> Image.Image:
    angle = randomizer.uniform(-0.9, 0.9)
    degraded = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=background)
    degraded = degraded.filter(ImageFilter.GaussianBlur(radius=randomizer.uniform(0.2, 0.5)))
    degraded = _apply_grain(degraded, randomizer)
    degraded = ImageEnhance.Contrast(degraded).enhance(0.96)
    degraded = ImageEnhance.Brightness(degraded).enhance(0.99)
    return degraded


def _draw_document(
    randomizer: random.Random,
    title: str,
    body_lines: list[str],
    footer: str,
    font_path: Path,
    template_id: str,
) -> Image.Image:
    handwritten = template_id == "handwritten_note"
    background = (246, 241, 230) if not handwritten else (243, 235, 220)
    image = _paper_background(randomizer, CANVAS_SIZE, "handwritten" if handwritten else "printed")
    draw = ImageDraw.Draw(image)

    title_font = _load_font(font_path, 62 if not handwritten else 66)
    body_font = _load_font(font_path, 42 if not handwritten else 46)
    footer_font = _load_font(font_path, 28)

    title_x = CANVAS_SIZE[0] - PAPER_MARGIN - randomizer.randint(0, 24)
    title_y = PAPER_MARGIN + randomizer.randint(4, 24)
    draw.text((title_x, title_y), title, font=title_font, fill=(34, 29, 24), anchor="ra")

    body_top = title_y + (132 if not handwritten else 118)
    max_width = CANVAS_SIZE[0] - (2 * PAPER_MARGIN) - 40
    wrapped_lines: list[str] = []
    for line in body_lines:
        wrapped_lines.extend(_wrap_hebrew_text(draw, line, body_font, max_width))

    line_height = 76 if handwritten else 68
    start_x = CANVAS_SIZE[0] - PAPER_MARGIN - randomizer.randint(0, 20)
    for index, line in enumerate(wrapped_lines):
        x = start_x - randomizer.randint(0, 10 if handwritten else 4)
        y = body_top + index * line_height + randomizer.randint(-3, 3 if handwritten else 1)
        draw.text((x, y), line, font=body_font, fill=(33, 28, 23), anchor="ra")

    footer_x = CANVAS_SIZE[0] - PAPER_MARGIN - randomizer.randint(12, 48)
    footer_y = CANVAS_SIZE[1] - PAPER_MARGIN - randomizer.randint(8, 24)
    draw.text((footer_x, footer_y), footer, font=footer_font, fill=(93, 82, 70), anchor="ra")

    return _degrade(image, randomizer, background)


def _select_font(fonts: list[dict], template_id: str) -> dict:
    target_style = "handwritten_like" if template_id == "handwritten_note" else "printed"
    for font in fonts:
        if font.get("style") == target_style:
            return font
    raise ValueError(f"No synthetic font registered for style: {target_style}")


def _select_title(template_id: str, index: int) -> str:
    titles = HANDWRITTEN_TITLES if template_id == "handwritten_note" else PRINTED_TITLES
    return titles[index % len(titles)]


def _select_body_lines(randomizer: random.Random, corpus: list[str], template_id: str) -> list[str]:
    line_count = 3 if template_id == "handwritten_note" else 4
    return randomizer.sample(corpus, k=min(line_count, len(corpus)))


def _footer_text(randomizer: random.Random) -> str:
    return f"{FOOTER_LABELS[randomizer.randrange(len(FOOTER_LABELS))]} {randomizer.randint(12, 128)}"


def generate_documents(
    count: int,
    seed: int,
    template_ids: list[str],
    font_manifest_path: Path,
    text_corpus_path: Path,
    output_dir: Path,
) -> list[SyntheticDocument]:
    randomizer = random.Random(seed)
    font_manifest = load_font_manifest(font_manifest_path)
    fonts = font_manifest.get("fonts")
    if not isinstance(fonts, list):
        raise ValueError(f"Synthetic font manifest is missing a valid 'fonts' list: {font_manifest_path}")
    corpus = load_text_corpus(text_corpus_path)
    if not template_ids:
        raise ValueError("Synthetic generation requires at least one template_id.")
    if not fonts:
        raise ValueError(f"Synthetic font manifest has no registered fonts: {font_manifest_path}")
    if not corpus:
        raise ValueError(f"Synthetic text corpus is empty: {text_corpus_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    documents: list[SyntheticDocument] = []
    for index in range(count):
        template_id = template_ids[index % len(template_ids)]
        font_entry = _select_font(fonts, template_id)
        font_path = _font_path(font_manifest_path, font_entry)
        title = _select_title(template_id, index)
        body_lines = _select_body_lines(randomizer, corpus, template_id)
        footer = _footer_text(randomizer)
        path = output_dir / f"synthetic_{seed}_{index}.jpg"
        image = _draw_document(
            randomizer=randomizer,
            title=title,
            body_lines=body_lines,
            footer=footer,
            font_path=font_path,
            template_id=template_id,
        )
        image.save(path, format="JPEG", quality=82, optimize=True)
        documents.append(
            SyntheticDocument(
                title=title,
                body="\n".join(body_lines),
                footer=footer,
                template_id=template_id,
                font_id=str(font_entry["id"]),
                path=path,
                sha256=sha256_file(path),
                generator_version=GENERATOR_VERSION,
            )
        )
    return documents
