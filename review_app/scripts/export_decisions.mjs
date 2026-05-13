#!/usr/bin/env node
// Export review decisions from the heocr-review D1 database into
// review_data/manual_decisions/<review_item_id>.json, matching the
// ReviewDecisionRecord shape in src/hocrgen/manifests/models.py.
//
// Usage:
//   node review_app/scripts/export_decisions.mjs \
//     --batch-id <batch_id> \
//     [--output-dir PATH]

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const ARGS = parseArgs(process.argv.slice(2));
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
  const outPath = join(OUTPUT_DIR, `${row.review_item_id}.json`);
  writeFileSync(outPath, JSON.stringify(record, null, 2) + "\n", "utf-8");
  written += 1;
}

console.log(`Exported ${written} decisions from batch ${BATCH_ID} to ${OUTPUT_DIR}.`);
if (written === 0) {
  console.log("No decisions found for this batch yet — nothing to apply.");
}

function parseWranglerJson(text) {
  // wrangler d1 execute --json prints an array of result objects with a `results` field.
  // Fall back to scanning the output if it is wrapped in informational lines.
  const trimmed = text.trim();
  const firstBracket = trimmed.indexOf("[");
  const lastBracket = trimmed.lastIndexOf("]");
  if (firstBracket === -1 || lastBracket === -1) {
    fail(`could not parse wrangler --json output:\n${text}`);
  }
  const payload = JSON.parse(trimmed.slice(firstBracket, lastBracket + 1));
  const out = [];
  for (const block of payload) {
    if (Array.isArray(block?.results)) {
      out.push(...block.results);
    }
  }
  return out;
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
