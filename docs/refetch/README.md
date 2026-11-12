# Re-fetch manifests for trashed Internet Archive page images

On 2026-11-12 the Internet Archive page images used by the F8f aligner runs were moved out of the HeOCR agent
workspace to free disk space (heocr-lead's approval, Shay's request). The workspace is not under git, so these
manifests are the lasting record of exactly which files existed and how to get them back.

| File | Covers | Files | Rows with a source hash |
|---|---|---:|---:|
| `ia_images_refetch_manifest.jsonl.gz` | `f8f_ia/work`, `f8f_g/work`, `f8f_g/ia_reprobe` (inputs of bynli_lines_v1–v3) | 20,341 | 16,652 |
| `rab_ia_images_refetch_manifest.jsonl.gz` | `f8f_rab/work` (inputs of rablines_v1) | 7,127 | 2,886 |

Paths are relative to `tasks/real-source-mapping/intermediates/f8f/` in the workspace. The first line of each file is
a `_meta` record; every other line is one file:

- `ia_identifier`, `file`, `path`, `kind`: which IA item the file belongs to and where it lived.
- `sha256`, `bytes`: the stored file exactly as it was on disk.
- `canvas_index`, `source`, `full_sha256`, `full_size` (page images only): from the record's `img_sources.json`.
  `full_sha256` is the hash of the original IA download before it was resized.

Only images moved. The OCR TSVs, `img_sources.json`, alignment outputs, `editions.json` and the rights-justification
records stayed in place, and the released line sets keep their own crops.

## How the images were made, and how to re-fetch them

The fetch scripts are `f8f_ia/scripts/ia_pages.py`, `f8f_g/scripts/g_fetch.py` and `f8f_rab/scripts/rab_pages.py`.
For canvas `k` of IA item `<id>`:

1. **`source: ia_page_download`.** GET `https://archive.org/download/<id>/page/n<k>_w1600.jpg`. IA serves the full-size
   leaf, and its sha256 is `full_sha256`. Check the aspect ratio against the IIIF canvas (within 0.5%). Resize to a
   width of `min(1600, canvas width)` with Pillow LANCZOS, convert to RGB and save as JPEG quality 92 as `img/c<k:04d>.jpg`.
2. **`source: iiif`.** GET `<canvas image service>/full/<width>,/0/default.jpg`, taking the service from the IA IIIF v3
   manifest `https://iiif.archive.org/iiif/3/<id>/manifest.json`. Store the bytes as they arrive.
3. **`source: ia_page_fallback`.** The page fallback path in the scripts above.

**To verify a re-fetch:**
- For `ia_page_download`, check the download against `full_sha256`. That check is exact. The resized JPEG's `sha256`
  matches only if the Pillow/libjpeg versions match, so treat it as a check, not a requirement.
- For `iiif` rows, check `sha256` directly. If IA re-encodes its derivatives this can drift, so compare `full_size`
  and the image dimensions as the fallback.
- `derived_crop` and `derived_or_page_png` rows (for example `foot/*.png`) are crops the scripts cut from the pages.
  Regenerate them from the pages instead of fetching them.

Fetch politely: send the generic `HeOCR-research/0.1 (+https://github.com/HeOCR)` User-Agent, keep at least 1 s
between requests, and stop on a 5xx or 429.

— data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource
