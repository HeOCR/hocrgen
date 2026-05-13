#!/usr/bin/env node
// Export review decisions from the heocr-review D1 database into
// review_data/manual_decisions/<sanitized_review_item_id>.json, matching the
// ReviewDecisionRecord shape in src/hocrgen/manifests/models.py.
//
// review_item_id values look like "review:<item_id>"; the colon is portable on
// macOS/Linux but breaks Windows tooling. We replace any character outside
// [A-Za-z0-9._-] with "_" for the filename. The original id is preserved in
// the JSON payload.
//
// Usage:
//   node review_app/scripts/export_decisions.mjs \
//     --batch-id <batch_id> \
//     [--output-dir PATH]

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";

import { parseArgs, runWrangler, fail } from "./_lib.mjs";

const ARGS = parseArgs({
  "batch-id": { type: "string" },
  "output-dir": { type: "string" },
});
if (!ARGS["batch-id"]) {
  fail("missing required --batch-id <batch_id>");
}
const BATCH_ID = ARGS["batch-id"];

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_OUTPUT_DIR = resolve(SCRIPT_DIR, "..", "..", "review_data", "manual_decisions");
const OUTPUT_DIR = ARGS["output-dir"] ? resolve(ARGS["output-dir"]) : DEFAULT_OUTPUT_DIR;

mkdirSync(OUTPUT_DIR, { recursive: true });

const sql = `SELECT review_item_id, item_id, decision, reviewer_email, decided_at, rationale, notes FROM review_decisions WHERE batch_id = '${BATCH_ID.replace(/'/g, "''")}'`;

const stdout = runWrangler(["d1", "execute", "heocr-review-db", "--remote", "--json", "--command", sql]);
const rows = parseWranglerJson(stdout);

let written = 0;
for (const row of rows) {
  const record = {
    review_item_id: row.review_item_id,
    item_id: row.item_id,
    decision: row.decision,
    reviewer: row.reviewer_email,
    timestamp: row.decided_at,
    rationale: row.rationale,
    notes: row.notes ?? null,
  };
  const outPath = join(OUTPUT_DIR, `${sanitizeForFilename(row.review_item_id)}.json`);
  writeFileSync(outPath, JSON.stringify(record, null, 2) + "\n", "utf-8");
  written += 1;
}

console.log(`Exported ${written} decisions from batch ${BATCH_ID} to ${OUTPUT_DIR}.`);
if (written === 0) {
  console.log("No decisions found for this batch yet — nothing to apply.");
}

function parseWranglerJson(text) {
  const trimmed = text.trim();
  let payload;
  try {
    payload = JSON.parse(trimmed);
  } catch (err) {
    fail(`could not parse wrangler --json output (${err.message}):\n${text}`);
  }
  if (!Array.isArray(payload)) {
    fail(`unexpected wrangler --json output shape:\n${text}`);
  }
  const out = [];
  for (const block of payload) {
    if (Array.isArray(block?.results)) {
      out.push(...block.results);
    }
  }
  return out;
}

function sanitizeForFilename(value) {
  return String(value).replace(/[^A-Za-z0-9._-]/g, "_");
}
