from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from hocrgen.config.loader import load_yaml_file
from hocrgen.utils.hashing import sha256_file


@dataclass(frozen=True)
class SyntheticDocument:
    title: str
    body: str
    footer: str
    template_id: str
    font_id: str
    path: Path
    sha256: str


HEBREW_TITLES = [
    "דו\"ח קבלה",
    "רשימת תיעוד",
    "פנקס משלוחים",
    "אישור מסירה",
]

ENGLISH_FRAGMENTS = ["Ref. 104", "Batch A", "Office Copy", "Page 1"]


def load_font_manifest(path: Path) -> dict:
    data = load_yaml_file(path)
    return data


def load_text_corpus(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _svg_document(title: str, body_lines: list[str], footer: str, font_family: str, background: str) -> str:
    body = "\n".join(
        f'<text x="560" y="{170 + index * 46}" text-anchor="end">{line}</text>'
        for index, line in enumerate(body_lines)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100" viewBox="0 0 800 1100">'
        f'<rect width="800" height="1100" fill="{background}" />'
        '<rect x="70" y="70" width="660" height="960" fill="#fffdf7" stroke="#cabfae" stroke-width="2" rx="12" />'
        f'<g font-family="{font_family}" fill="#231f1a">'
        f'<text x="560" y="120" text-anchor="end" font-size="34" font-weight="700">{title}</text>'
        f'<g font-size="28">{body}</g>'
        f'<text x="560" y="980" text-anchor="end" font-size="20" fill="#6b6156">{footer}</text>'
        "</g></svg>"
    )


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
    fonts = font_manifest["fonts"]
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
        font = fonts[index % len(fonts)]
        background = "#f8f1e3" if template_id == "printed_letter" else "#f3ece1"
        title = HEBREW_TITLES[index % len(HEBREW_TITLES)]
        english = ENGLISH_FRAGMENTS[index % len(ENGLISH_FRAGMENTS)]
        selected = randomizer.sample(corpus, k=min(3, len(corpus)))
        body_lines = [selected[0], selected[1] if len(selected) > 1 else selected[0], f"{selected[-1]} | {english}"]
        footer = f"synthetic-seed-{seed}-{index}"
        path = output_dir / f"synthetic_{seed}_{index}.svg"
        path.write_text(
            _svg_document(title=title, body_lines=body_lines, footer=footer, font_family=font["css_family"], background=background),
            encoding="utf-8",
        )
        documents.append(
            SyntheticDocument(
                title=title,
                body="\n".join(body_lines),
                footer=footer,
                template_id=template_id,
                font_id=font["id"],
                path=path,
                sha256=sha256_file(path),
            )
        )
    return documents
