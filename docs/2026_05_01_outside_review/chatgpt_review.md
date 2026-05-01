## **Bottom line**

The earlier “Milestone 3 only” description is now stale. The current hocrgen repo has progressed well beyond acquisition + normalization + QA. Its README and roadmap now describe completed layers for exact dedupe, classification, privacy screening, review queues, split assignment, benchmark subset selection, evaluation helpers, annotation-pilot selection, source maintenance, NLI seed promotion, alpha export, and release governance. However, it is still not yet a large-scale dataset generator or benchmark platform in the practical sense: it is still conservative, fixture/sample-backed, and missing large real-source acquisition, near-duplicate detection, OCR/HTR ground truth, modern handwritten data acquisition, OCR-aware privacy review, robust benchmark references, and final publication/training infrastructure.

I did not execute the repo locally in this session; this is based on current public GitHub code/docs inspection.

## **1\. Does the implementation status you described still hold?**

**Partly, but it is outdated.**

Your earlier summary was accurate for the point after Milestone 3, but the current repo now claims and implements more than that. The README says the toolchain now includes policy/review, source operations, benchmark subset handling, evaluation utilities, community contribution support, annotation-pilot selection, and multi-release governance on top of the earlier acquisition, normalization, QA, and curation layers.

The roadmap also marks phases through **E4** as completed, while explicitly warning that “pipeline-complete,” “content-complete,” and “release-ready” are separate concepts. That warning is important: the codebase has many release-management mechanisms, but that does not mean the project already has enough real, diverse, annotated Hebrew OCR data for a mature public benchmark.

The still-true part of your prior conclusion is:

The pipeline is healthy for controlled pilot runs, but not yet enough for a mature, large public Hebrew OCR/HTR dataset and benchmark.

What changed is that several previously missing governance pieces now exist in code: exact dedupe, review export/merge, benchmark subset logic, annotation-pilot selection, alpha export, and source-promotion tooling. The remaining gap is less “basic pipeline scaffolding” and more “scale, uniqueness, annotation, modern handwritten data, benchmark validity, and publication maturity.”

## **2\. Is it ready for a first real multi-item NLI seed run?**

**Yes, but only for fixture-backed seeds.**

The current NLI fetcher does **not** live-fetch arbitrary NLI URLs during hocrgen build-release. It loads a YAML seed manifest, expects each buildable seed to have id and url, and for actual metadata fetching it requires fixture_html. If a seed lacks fixture_html, the fetcher raises an error saying live fetching is not implemented yet.

So:

**Ready now:**

uv run hocrgen build-release \\

\--profile profile_open_v1 \\

\--dry-run \\

\--source nli_any_use_permitted \\

\--max-items 7

This should exercise the currently committed NLI fixture-backed seeds.

**Not ready as a direct raw-URL run:**

items:

\- id: nli-ms-seed-008

url: ...

That is not enough for build-release. Raw candidate URLs first need to be promoted into local fixtures/assets using the NLI promotion script.

The repo currently separates NLI data into:

1.  src/hocrgen/data/nli/seeds.yaml — runnable fixture-backed seeds.
2.  src/hocrgen/data/nli/seed_catalog.yaml — broader exploratory candidate URLs that are not directly runnable until promoted.

That is the main practical blocker to understand: **do not paste the old 20 raw URLs directly into seeds.yaml unless each one has a valid local fixture_html.**

## **3\. Exact NLI seed manifest format**

There are effectively two schemas.

### **Runnable****seeds.yaml**

This is what build-release consumes.

items:

\- id: nli-ms-seed-001

url: https://...

title: Some title

fixture_html: package://data/nli/item_nli_ms_seed_001.html

notes: Optional notes

Required by code:

id: string

url: string

Required in practice for build-release:

fixture_html: string

Optional:

title: string

notes: string

The code accepts fixture_html as package://..., absolute path, or relative path. Without it, the NLI fetcher errors because live fetching is not implemented inside the normal pipeline.

### **Exploratory****seed_catalog.yaml**

This is for candidates not yet promoted.

items:

\- id: nli-ms-seed-013

url: https://...

title: Some title

notes: Strong candidate; item page shows explicit download options.

This file is for the promotion workflow, not for direct dataset builds. The promotion script loads candidate seeds, captures the page/assets, validates rights, writes local fixtures/assets, updates runnable seeds, and emits a report.

## **4\. Does the earlier 20-item draft need adaptation?**

Yes. The adaptation is:

- fixture-backed items belong in seeds.yaml;
- raw candidate URLs belong in seed_catalog.yaml;
- after promotion, the tool writes promoted entries back into runnable seed format.

The current repo already appears to have this split. seeds.yaml contains the committed runnable NLI fixture-backed seeds, while seed_catalog.yaml contains the remaining candidate-only items such as nli-ms-seed-005 and nli-ms-seed-008 through nli-ms-seed-020.

Do **not** replace the current seeds.yaml with a 20-item raw URL list. That would regress the repo and likely break the build.

The correct candidate-only format for the unpromoted portion is:

items:

\- id: nli-ms-seed-005

url: "&lt;NLI item URL&gt;"

title: "פנקס"

notes: "Candidate-only until promoted."

\- id: nli-ms-seed-013

url: "&lt;NLI item URL&gt;"

title: "מגלת אסתר"

notes: "Strong candidate; item page shows explicit download options."

\- id: nli-ms-seed-015

url: "&lt;NLI item URL&gt;"

title: "תכלאל"

notes: "Candidate-only until promoted."

\- id: nli-ms-seed-018

url: "&lt;NLI item URL&gt;"

title: "העתקי כתבי-יד"

notes: "Candidate-only until promoted."

\- id: nli-ms-seed-019

url: "&lt;NLI item URL&gt;"

title: "שטרות, תנאים וכתובות"

notes: "Document-heavy seed."

Use the actual URLs already present in seed_catalog.yaml; the promotion script should then write entries like this into seeds.yaml after successful capture:

items:

\- id: nli-ms-seed-005

url: "&lt;NLI item URL&gt;"

title: "פנקס"

fixture_html: package://data/nli/item_nli_ms_seed_005.html

notes: "Candidate-only until promoted."

## **5\. Best first real seed batch**

For the immediate next run, I would use two steps.

### **Step A — run the already fixture-backed NLI seeds**

Use all currently runnable NLI seeds first:

uv run hocrgen build-release \\

\--profile profile_open_v1 \\

\--dry-run \\

\--source nli_any_use_permitted \\

\--max-items 7

Reason: this tests the multi-item NLI path without browser capture, Cloudflare, asset-download, or rights-extraction uncertainty.

### **Step B — promote 5 additional catalog candidates**

Recommended first promotion batch:

nli-ms-seed-005

nli-ms-seed-013

nli-ms-seed-015

nli-ms-seed-018

nli-ms-seed-019

Why this batch:

- 005 / 019 look more document- or ledger-like.
- 013 is explicitly noted in the repo catalog as a strong candidate with clear download options.
- 015 adds Yemenite manuscript/prayer-book style diversity.
- 018 adds manuscript-copy material.
- This avoids making the first expansion batch mostly ketubot or decorative megillot, which may be less representative for OCR/HTR stress testing despite being visually useful.

This still does **not** solve the project’s modern-handwritten identity. These NLI candidates are useful acquisition-system tests and historical manuscript coverage, not a substitute for rights-clean modern handwritten Hebrew.

## **6\. Exact commands to run with****uv**

The project requires Python >=3.11, not 3.10. The repo has a pyproject.toml with runtime deps on defusedxml, Pillow, pydantic, and PyYAML; playwright is not listed as a normal project dependency.

### **Validate local environment**

uv sync --extra dev

uv run hocrgen config validate

### **First NLI-only fixture-backed build**

uv run hocrgen build-release \\

\--profile profile_open_v1 \\

\--dry-run \\

\--source nli_any_use_permitted \\

\--max-items 7

If this fails because the benchmark gate expects non-NLI benchmark items, run the NLI-only pipeline only up to split first:

uv run hocrgen split \\

\--profile profile_open_v1 \\

\--dry-run \\

\--source nli_any_use_permitted \\

\--max-items 7

Reason: the current benchmark_v1 config explicitly approves one NLI item, one Pinkas item, and one synthetic item. A source-filtered NLI-only build-release may therefore conflict with benchmark completeness depending on how the current CLI path handles filtered builds.

### **Inspect latest run**

export RUN="$(ls -td .work/hocrgen/runs/\* | head -1)"

python - <<'PY'

import json

import os

from pathlib import Path

run = Path(os.environ\["RUN"\])

for rel in \[

"discover/summary.json",

"fetch_metadata/summary.json",

"policy_filter/summary.json",

"acquire/summary.json",

"normalize/summary.json",

"dedupe/summary.json",

"privacy_scan/summary.json",

"review_merge/summary.json",

"split/summary.json",

"build_release/release_summary.json",

"build_release/source_stats.json",

"build_release/benchmark_selection_audit.json",

\]:

p = run / rel

if not p.exists():

print(f"\\n# missing: {rel}")

continue

print(f"\\n# {rel}")

print(json.dumps(json.loads(p.read_text()), ensure_ascii=False, indent=2))

PY

### **Install Playwright for NLI promotion**

uv pip install playwright

uv run playwright install chromium

The promotion tool itself suggests this if Playwright is missing.

### **Dry-run promotion of the first five catalog candidates**

uv run python scripts/promote_nli_seeds.py \\

\--seed-id nli-ms-seed-005 \\

\--seed-id nli-ms-seed-013 \\

\--seed-id nli-ms-seed-015 \\

\--seed-id nli-ms-seed-018 \\

\--seed-id nli-ms-seed-019 \\

\--browser-state-dir .cache/nli-playwright \\

\--report-path src/hocrgen/data/nli/promotion_report.json \\

\--dry-run

### **Actual promotion**

uv run python scripts/promote_nli_seeds.py \\

\--seed-id nli-ms-seed-005 \\

\--seed-id nli-ms-seed-013 \\

\--seed-id nli-ms-seed-015 \\

\--seed-id nli-ms-seed-018 \\

\--seed-id nli-ms-seed-019 \\

\--browser-state-dir .cache/nli-playwright \\

\--report-path src/hocrgen/data/nli/promotion_report.json

### **If NLI blocks automated capture**

The README documents a Chrome DevTools Protocol path for browser-assisted promotion. Use this if Cloudflare/session state blocks normal capture.

/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\

\--remote-debugging-port=9222 \\

\--user-data-dir=/tmp/hocrgen-chrome

Then:

uv run python scripts/promote_nli_seeds.py \\

\--seed-id nli-ms-seed-005 \\

\--seed-id nli-ms-seed-013 \\

\--seed-id nli-ms-seed-015 \\

\--seed-id nli-ms-seed-018 \\

\--seed-id nli-ms-seed-019 \\

\--connect-cdp http://127.0.0.1:9222 \\

\--manual-wait-timeout 90 \\

\--pause-on-every-challenge \\

\--report-path src/hocrgen/data/nli/promotion_report.json

### **Build again after promotion**

If the five promotions succeed, current runnable NLI seed count should become roughly 12: the existing runnable seeds plus the five newly promoted seeds.

uv run hocrgen build-release \\

\--profile profile_open_v1 \\

\--dry-run \\

\--source nli_any_use_permitted \\

\--max-items 12

## **7\. What successful output should look like**

For the fixture-backed NLI-only run:

- discover/summary.json should show multiple NLI candidates, ideally 7 for the current fixture-backed seed set.
- fetch_metadata/summary.json should show fetched/enriched metadata without missing fixtures.
- policy_filter/summary.json should show accepted items and no rights-based rejections.
- acquire/summary.json should show acquired item count equal to the accepted count.
- normalize/summary.json should show normalized item count equal to acquired count and failed_count: 0.
- dedupe/summary.json should show retained count close to normalized count; ideally no unexpected duplicates.
- privacy_scan and review_merge should not leave unexpected unresolved items for anything you intend to release.
- split/summary.json should assign release-ready items to splits.
- build_release should write release manifests, source stats, benchmark artifacts, and review artifacts.

The pipeline stages are explicitly wired through discover, fetch-metadata, policy-filter, acquire, normalize, dedupe, classify, privacy-scan, review-export, review-merge, split, and build-release.

Red flags:

- missing fixture_html or “live fetching is not implemented yet.”
- NLI promotion report shows rights_missing, rights_not_allowed, assets_missing, or challenge_not_resolved.
- Asset count is zero for promoted items.
- Normalization failures.
- A high duplicate count from supposedly diverse seeds.
- Privacy/review unresolved items for public release candidates.
- Benchmark failure caused by source-filtering away approved benchmark items.
- NLI pages that are visually decorative, sparse, or non-textual despite passing rights checks.
- The run succeeds technically but all examples are historical manuscripts; that is fine for acquisition testing, but not for the dataset’s modern-heavy target.

## **8\. What is missing for a large, unique, real+synthetic Hebrew OCR dataset and benchmark?**

### **A. Large-scale real acquisition**

The repo still does not contain a broad crawler. The NLI path is a conservative seed-manifest and promotion workflow; CI/release builds remain fixture-backed and network-free. The README explicitly describes broad live-source crawling as future work.

Missing pieces:

- scalable source discovery beyond hand-curated seeds;
- robust NLI/API/IIIF harvesting where permitted;
- resumable downloads;
- rate limiting and retry policy;
- asset/page selection rules;
- source-level quotas;
- storage strategy for hundreds/thousands of pages;
- source failure dashboards;
- provenance validation at scale.

### **B. Modern handwritten Hebrew data**

The project’s stated identity is modern handwritten Hebrew, but the currently available public-source path is mostly historical NLI/Pinkas/BiblIA plus synthetic. The roadmap itself says modern handwritten Hebrew is the core identity and that source scaling should not outrun review, QA, and release discipline.

Missing pieces:

- rights-clean modern handwriting collection;
- contributor release forms or institutional agreements;
- scanning/upload standards;
- privacy screening for contemporary documents;
- consent/takedown workflow;
- demographic/script-style diversity targets;
- modern page types: notes, forms, letters, school/work material, mixed Hebrew/English.

This is probably the biggest content gap.

### **C. OCR/HTR ground truth**

The repo has benchmark and evaluation scaffolding, but a serious benchmark requires references: page/line/word transcriptions, normalization rules, and split-stable labels. The README describes evaluation utilities that compare predictions against references and annotation-pilot selection, but this is not the same as already having a large labeled benchmark.

Missing pieces:

- transcription guidelines for Hebrew, niqqud, punctuation, numbers, Latin text, abbreviations, and bidi;
- line/page segmentation policy;
- annotation tooling;
- reviewer/adjudication workflow;
- inter-annotator agreement checks;
- reference manifests;
- benchmark labels committed or published separately;
- baseline OCR/HTR model outputs.

Without ground truth, the project can generate a dataset of images/manifests, but not a meaningful OCR benchmark.

### **D. Near-duplicate and leakage control**

The repo now has exact item-level dedupe, but the README explicitly says perceptual/semantic near-duplicate detection and OCR-aware grouping are future work.

Missing pieces:

- perceptual hashing;
- layout/image similarity;
- OCR-text similarity once OCR is available;
- source/work-level grouping;
- split leakage prevention by manuscript/book/source family;
- synthetic/real contamination checks;
- benchmark holdout leakage audits.

Exact checksum dedupe is not enough for a benchmark.

### **E. OCR-aware quality and privacy screening**

The repo has technical QA and metadata-driven privacy screening, but not OCR-aware content inspection. The README explicitly calls out OCR-aware privacy screening and advanced classification/model-training as future work.

Missing pieces:

- blur/skew/crop/text-density scoring;
- page orientation detection;
- handwritten/printed/mixed classifier;
- text-region detection;
- detection of blank/decorative pages;
- PII detection from OCR text;
- sensitive content review queues.

### **F. Synthetic realism and synthetic governance**

Synthetic SVG/JPEG generation exists and is now governed/reported, but synthetic data is not yet enough to support a credible benchmark by itself. The repo has synthetic composition reporting and release caps, but large synthetic generation still needs realism validation against real data.

Missing pieces:

- richer Hebrew handwriting-like generation;
- font/style diversity;
- document-layout templates;
- synthetic noise/scanner artifacts matched to real distributions;
- mixed Hebrew/English examples;
- controlled label generation;
- synthetic-vs-real reporting by split;
- policy that synthetic examples do not dominate benchmark conclusions.

### **G. Benchmark maturity**

The current benchmark_v1 is explicitly tiny: one NLI item, one Pinkas item, and one synthetic item.

Missing pieces:

- larger stable benchmark sets;
- separate tracks: modern handwritten, historical handwritten, printed, mixed synthetic;
- fixed public references or controlled hidden references;
- baseline OCR/HTR systems;
- scoring scripts with CER/WER and Hebrew-specific normalization;
- leaderboard or reproducible evaluation protocol;
- benchmark versioning policy when items are removed or corrected.

### **H. Final publication pipeline**

The repo now has alpha export support, but final publication to a mature public dataset destination remains future work. The README lists final publication to Hugging Face/GitHub dataset repo and full packaging maturity as future work.

Missing pieces:

- durable storage strategy;
- released dataset repo structure;
- versioned manifests;
- dataset card;
- license/rights summaries;
- checksums;
- downloadable archives;
- public review queue or issue workflow;
- takedown/rollback process;
- release changelog and diff artifacts tied to actual published versions.

## **9\. Code changes needed**

For the **next small NLI run**, probably no code changes are needed. Use the existing fixture-backed seeds and the promotion script.

For a **raw 20-URL direct build**, code changes would be needed unless you go through promotion first. The current NLI fetcher explicitly does not live-fetch missing fixtures during normal pipeline execution.

For a **large benchmark-grade dataset**, code changes are needed in these areas:

1.  Add or formalize a scalable acquisition mode separate from the fixture-backed release path.
2.  Add perceptual/near-duplicate dedupe.
3.  Add page-level quality classifiers.
4.  Add OCR-assisted privacy screening.
5.  Add annotation/reference-ground-truth workflow.
6.  Add benchmark scoring with stable references and baseline outputs.
7.  Add real modern-handwriting contribution/acquisition tooling.
8.  Add data-versioning/publication integration for the separate HeOCR dataset repo.

## **10\. Most sensible next milestone**

The current roadmap notation appears to have completed A1–E4, so the next practical milestone should be a new post-E4 milestone. I would define it as:

## **F1 — Real-data scale pilot and benchmark-ground-truth foundation**

Scope:

1.  Promote 20–50 NLI/Pinkas/BiblIA/open historical items through the existing conservative fixture workflow.
2.  Add a run report that summarizes promotion failures by reason: rights, assets, challenge, parse failure, normalization failure, duplicate.
3.  Add perceptual dedupe before increasing beyond 50–100 real items.
4.  Select 10–25 release-ready real pages for a first annotation pilot.
5.  Write transcription guidelines for Hebrew OCR/HTR.
6.  Produce a tiny but real benchmark with references, not just image manifests.
7.  Keep synthetic data present but capped and clearly reported.

After that, define:

## **F2 — Modern handwritten acquisition**

This should focus on project-owned or contributor-released modern Hebrew handwriting. That is the missing content class most central to the project’s intended identity.
