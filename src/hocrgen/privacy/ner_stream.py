"""Tag person names (PER) in line streams with dicta-il/dictabert-ner (CC BY 4.0); a filter only, never training input.

Standalone (stdlib + torch + transformers, no hocrgen import), run in the NER venv with ``-I``:

    ~/.venvs/heocr-ner/bin/python -I ner_stream.py IN.jsonl OUT.jsonl

Input rows: ``{"id", "text"}``, where ``text`` is ``hocrgen.privacy.plenary_names.stream_text`` of a page's lines.
Output rows: ``{"id", "person_spans": [{"start", "end", "text", "score"}], "model", "model_revision"}``, with spans in
the coordinates of that exact text. Long texts are tagged in overlapping windows (``WINDOW`` characters, cut at a space,
``OVERLAP`` characters shared), so a name at a window edge is seen whole in one of them.
"""

import json
import sys

MODEL = "dicta-il/dictabert-ner"
WINDOW = 700
OVERLAP = 150


def windows(text, size=WINDOW, overlap=OVERLAP):
    """(offset, chunk) windows of at most ``size`` characters, each starting ``overlap`` before the last one ended."""
    if len(text) <= size:
        yield 0, text
        return
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            cut = text.rfind(" ", start + overlap + 1, end)
            if cut > start:
                end = cut
        yield start, text[start:end]
        if end >= len(text):
            return
        nxt = text.rfind(" ", start, end - overlap)
        start = nxt + 1 if nxt > start else end


def main(src, dst):
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForTokenClassification.from_pretrained(MODEL, use_safetensors=True)
    revision = getattr(model.config, "_commit_hash", None)
    ner = pipeline("token-classification", model=model, tokenizer=tokenizer, aggregation_strategy="simple", device=device)
    rows = [json.loads(line) for line in open(src, encoding="utf-8") if line.strip()]
    batch = [(i, off, chunk) for i, row in enumerate(rows) for off, chunk in windows(row["text"])]
    results = ner([chunk for _, _, chunk in batch], batch_size=32) if batch else []
    spans = {i: {} for i in range(len(rows))}
    for (i, off, _), ents in zip(batch, results):
        text = rows[i]["text"]
        for ent in ents:
            if ent["entity_group"] != "PER":
                continue
            s, e = off + int(ent["start"]), off + int(ent["end"])
            key = (s, e)
            score = round(float(ent["score"]), 4)
            if key not in spans[i] or spans[i][key]["score"] < score:
                spans[i][key] = {"start": s, "end": e, "text": text[s:e], "score": score}
    with open(dst, "w", encoding="utf-8") as out:
        for i, row in enumerate(rows):
            found = [spans[i][k] for k in sorted(spans[i])]
            out.write(json.dumps({"id": row["id"], "person_spans": found, "model": MODEL, "model_revision": revision},
                                 ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
