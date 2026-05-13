#!/usr/bin/env node
// Seed a review batch into the heocr-review D1 database.
//
// Usage:
//   node review_app/scripts/seed_batch.mjs \
//     --queue-file PATH \
//     [--run-dir PATH] \
//     [--batch-label TEXT] \
//     [--dataset-version TEXT] \
//     [--milestone TEXT] \
//     [--active-blockers N] \
//     [--benchmark-coverage TEXT]

import { readFileSync, existsSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import sharp from "sharp";

import { parseArgs, runWrangler, sqlValue, fail } from "./_lib.mjs";

const ARGS = parseArgs({
  "queue-file": { type: "string" },
  "run-dir": { type: "string" },
  "batch-label": { type: "string" },
  "dataset-version": { type: "string" },
  "milestone": { type: "string" },
  "active-blockers": { type: "string" },
  "benchmark-coverage": { type: "string" },
});
if (!ARGS["queue-file"]) {
  fail("missing required --queue-file PATH");
}

const QUEUE_FILE = resolve(ARGS["queue-file"]);
const RUN_DIR = ARGS["run-dir"] ? resolve(ARGS["run-dir"]) : null;
const BATCH_LABEL = ARGS["batch-label"] ?? null;

const BATCH_ID = `batch-${new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z")}`;
const NOW_ISO = new Date().toISOString();

const queueRaw = JSON.parse(readFileSync(QUEUE_FILE, "utf-8"));
const items = Array.isArray(queueRaw?.items) ? queueRaw.items : [];
if (items.length === 0) {
  fail(`queue file ${QUEUE_FILE} has no items`);
}

console.log(`Seeding batch ${BATCH_ID} with ${items.length} items...`);

const preparedItems = [];
for (const item of items) {
  const previews = await renderPreviews(item.preview_paths ?? []);
  preparedItems.push({
    review_item_id: item.review_item_id,
    item_id: item.item_id,
    source_id: item.source_id,
    canonical_item_id: item.canonical_item_id,
    title: item.title ?? null,
    source_url: item.source_url ?? null,
    review_reasons: JSON.stringify(item.review_reasons ?? []),
    suggested_decision: item.suggested_decision,
    privacy_flag: typeof item.privacy_flag === "string" ? item.privacy_flag : (item.privacy_flag?.value ?? "unknown"),
    preview_b64: previews.preview_b64,
    full_image_b64: previews.full_image_b64,
    raw_record: JSON.stringify(item),
  });
}

const statsRows = collectStats({
  runDir: RUN_DIR,
  datasetVersion: ARGS["dataset-version"] ?? null,
  milestone: ARGS["milestone"] ?? null,
  activeBlockers: ARGS["active-blockers"] ?? null,
  benchmarkCoverage: ARGS["benchmark-coverage"] ?? null,
  batchLabel: BATCH_LABEL,
  batchId: BATCH_ID,
  itemCount: preparedItems.length,
});

// Phase 1: batch metadata + stats — small enough to fit in one --file execute,
// so it is atomic per file. This eliminates the previous race window where the
// old batch was already closed but the new one had not yet been inserted.
const metaStatements = [
  `UPDATE review_batches SET status = 'closed' WHERE status = 'active';`,
  `INSERT INTO review_batches (batch_id, batch_label, seeded_at, item_count, status) VALUES (${sqlValue(BATCH_ID)}, ${sqlValue(BATCH_LABEL)}, ${sqlValue(NOW_ISO)}, ${preparedItems.length}, 'active');`,
];
for (const [key, value] of Object.entries(statsRows)) {
  if (value == null) continue;
  metaStatements.push(
    `INSERT INTO pipeline_stats (key, value, updated_at) VALUES (${sqlValue(key)}, ${sqlValue(String(value))}, ${sqlValue(NOW_ISO)}) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;`,
  );
}

// Phase 2: per-item INSERTs are kept as separate --file invocations because
// base64 image blobs can push a combined file past D1's 5MB per-file limit.
// If a per-item insert fails the partial batch remains active and the operator
// must intervene manually (either rerun after fixing the cause or DELETE the
// partial batch); see review_app/README.md "Storage limitations" for context.
const itemStatements = preparedItems.map(
  (row) =>
    `INSERT INTO review_items (batch_id, review_item_id, item_id, source_id, canonical_item_id, title, source_url, review_reasons, suggested_decision, privacy_flag, preview_b64, full_image_b64, raw_record) VALUES (${sqlValue(BATCH_ID)}, ${sqlValue(row.review_item_id)}, ${sqlValue(row.item_id)}, ${sqlValue(row.source_id)}, ${sqlValue(row.canonical_item_id)}, ${sqlValue(row.title)}, ${sqlValue(row.source_url)}, ${sqlValue(row.review_reasons)}, ${sqlValue(row.suggested_decision)}, ${sqlValue(row.privacy_flag)}, ${sqlValue(row.preview_b64)}, ${sqlValue(row.full_image_b64)}, ${sqlValue(row.raw_record)});`,
);

let executed = 0;
const tmpDir = mkdtempSync(join(tmpdir(), "heocr-review-seed-"));
try {
  // Phase 1: atomic batch metadata.
  const metaFile = join(tmpDir, "00-batch-metadata.sql");
  writeFileSync(metaFile, metaStatements.join("\n") + "\n", "utf-8");
  runWrangler(["d1", "execute", "heocr-review-db", "--remote", "--file", metaFile]);
  executed += metaStatements.length;

  // Phase 2: per-item inserts.
  for (const [idx, stmt] of itemStatements.entries()) {
    const itemFile = join(tmpDir, `item-${idx}.sql`);
    writeFileSync(itemFile, stmt + "\n", "utf-8");
    runWrangler(["d1", "execute", "heocr-review-db", "--remote", "--file", itemFile]);
    executed += 1;
  }
} finally {
  rmSync(tmpDir, { recursive: true, force: true });
}

console.log(`Seeded batch ${BATCH_ID}: ${preparedItems.length} items, ${executed} SQL statements executed.`);

async function renderPreviews(paths) {
  for (const candidate of paths) {
    if (!candidate) continue;
    const abs = resolve(candidate);
    if (!existsSync(abs)) continue;
    try {
      const previewBuf = await sharp(abs).resize({ width: 300, withoutEnlargement: true }).jpeg({ quality: 85 }).toBuffer();
      const fullBuf = await sharp(abs).resize({ width: 1600, withoutEnlargement: true }).jpeg({ quality: 80 }).toBuffer();
      return {
        preview_b64: previewBuf.toString("base64"),
        full_image_b64: fullBuf.toString("base64"),
      };
    } catch (err) {
      console.warn(`failed to render preview for ${abs}: ${err.message}`);
    }
  }
  return { preview_b64: null, full_image_b64: null };
}

function collectStats({ runDir, datasetVersion, milestone, activeBlockers, benchmarkCoverage, batchLabel, batchId, itemCount }) {
  const stats = {
    last_batch_id: batchId,
    last_batch_label: batchLabel,
    last_batch_seeded_at: NOW_ISO,
    last_batch_item_count: itemCount,
  };

  if (datasetVersion != null) stats.dataset_version = datasetVersion;
  if (milestone != null) stats.milestone = milestone;
  if (activeBlockers != null) stats.active_blockers = activeBlockers;
  if (benchmarkCoverage != null) stats.benchmark_coverage = benchmarkCoverage;

  if (runDir) {
    const buildReleaseDir = join(runDir, "build_release");
    const sourceStats = readJsonIfExists(join(buildReleaseDir, "source_stats.json"));
    const releaseSummary = readJsonIfExists(join(buildReleaseDir, "release_summary.json"));
    const synthComposition = readJsonIfExists(join(buildReleaseDir, "synthetic_composition.json"));

    if (releaseSummary) {
      if (typeof releaseSummary.release_ready_item_count === "number") {
        stats.release_ready_items = releaseSummary.release_ready_item_count;
      }
      if (typeof releaseSummary.total_candidate_count === "number") {
        stats.total_candidates = releaseSummary.total_candidate_count;
      }
    }
    if (sourceStats?.retained_source_counts) {
      const counts = sourceStats.retained_source_counts;
      let real = 0;
      const sub = {};
      for (const [source, count] of Object.entries(counts)) {
        if (typeof count !== "number") continue;
        if (source === "project_synthetic") {
          stats.synthetic_items = count;
          continue;
        }
        sub[source] = count;
        real += count;
      }
      stats.real_items = real;
      stats.real_items_breakdown = JSON.stringify(sub);
    }
    if (synthComposition?.totals?.synthetic_item_count != null && stats.synthetic_items == null) {
      stats.synthetic_items = synthComposition.totals.synthetic_item_count;
    }
  }

  return stats;
}

function readJsonIfExists(path) {
  if (!existsSync(path)) return null;
  try {
    return JSON.parse(readFileSync(path, "utf-8"));
  } catch (err) {
    console.warn(`failed to parse ${path}: ${err.message}`);
    return null;
  }
}
