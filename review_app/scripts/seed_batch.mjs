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
import { spawnSync } from "node:child_process";
import sharp from "sharp";

const ARGS = parseArgs(process.argv.slice(2));
if (!ARGS["queue-file"]) {
  fail("missing required --queue-file PATH");
}

const QUEUE_FILE = resolve(ARGS["queue-file"]);
const RUN_DIR = ARGS["run-dir"] ? resolve(ARGS["run-dir"]) : null;
const BATCH_LABEL = ARGS["batch-label"] ?? null;
const DATASET_VERSION = ARGS["dataset-version"] ?? null;
const MILESTONE = ARGS["milestone"] ?? null;
const ACTIVE_BLOCKERS = ARGS["active-blockers"] ?? null;
const BENCHMARK_COVERAGE = ARGS["benchmark-coverage"] ?? null;

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
  datasetVersion: DATASET_VERSION,
  milestone: MILESTONE,
  activeBlockers: ACTIVE_BLOCKERS,
  benchmarkCoverage: BENCHMARK_COVERAGE,
  batchLabel: BATCH_LABEL,
  batchId: BATCH_ID,
  itemCount: preparedItems.length,
});

const sqlChunks = [];

sqlChunks.push(
  `UPDATE review_batches SET status = 'closed' WHERE status = 'active';`,
);
sqlChunks.push(
  `INSERT INTO review_batches (batch_id, batch_label, seeded_at, item_count, status) VALUES (${sqlValue(BATCH_ID)}, ${sqlValue(BATCH_LABEL)}, ${sqlValue(NOW_ISO)}, ${preparedItems.length}, 'active');`,
);
for (const row of preparedItems) {
  sqlChunks.push(
    `INSERT INTO review_items (batch_id, review_item_id, item_id, source_id, canonical_item_id, title, source_url, review_reasons, suggested_decision, privacy_flag, preview_b64, full_image_b64, raw_record) VALUES (${sqlValue(BATCH_ID)}, ${sqlValue(row.review_item_id)}, ${sqlValue(row.item_id)}, ${sqlValue(row.source_id)}, ${sqlValue(row.canonical_item_id)}, ${sqlValue(row.title)}, ${sqlValue(row.source_url)}, ${sqlValue(row.review_reasons)}, ${sqlValue(row.suggested_decision)}, ${sqlValue(row.privacy_flag)}, ${sqlValue(row.preview_b64)}, ${sqlValue(row.full_image_b64)}, ${sqlValue(row.raw_record)});`,
  );
}
for (const [key, value] of Object.entries(statsRows)) {
  if (value == null) continue;
  sqlChunks.push(
    `INSERT INTO pipeline_stats (key, value, updated_at) VALUES (${sqlValue(key)}, ${sqlValue(String(value))}, ${sqlValue(NOW_ISO)}) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;`,
  );
}

// D1 has SQL length limits and the per-item rows can be large (base64-encoded
// images). Execute each statement individually using --file PATH so we never
// quote large blobs through the shell.
let executed = 0;
const tmpDir = mkdtempSync(join(tmpdir(), "heocr-review-seed-"));
try {
  for (const stmt of sqlChunks) {
    const tmpFile = join(tmpDir, `stmt-${executed}.sql`);
    writeFileSync(tmpFile, stmt + "\n", "utf-8");
    runWrangler(["d1", "execute", "heocr-review-db", "--remote", "--file", tmpFile]);
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

function runWrangler(args) {
  const result = spawnSync("npx", ["wrangler", ...args], {
    stdio: ["ignore", "pipe", "pipe"],
    env: process.env,
  });
  if (result.status !== 0) {
    const stderr = result.stderr?.toString() ?? "";
    const stdout = result.stdout?.toString() ?? "";
    fail(`wrangler ${args.join(" ")} failed:\n${stderr}\n${stdout}`);
  }
  return result.stdout?.toString() ?? "";
}

function sqlValue(value) {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "number") return String(value);
  return "'" + String(value).replace(/'/g, "''") + "'";
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next === undefined || next.startsWith("--")) {
      out[key] = true;
    } else {
      out[key] = next;
      i += 1;
    }
  }
  return out;
}

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(1);
}
