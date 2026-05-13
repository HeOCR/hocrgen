// Shared helpers for seed_batch.mjs and export_decisions.mjs.

import { parseArgs as nodeParseArgs } from "node:util";
import { spawnSync } from "node:child_process";

export function parseArgs(optionSpec) {
  const { values } = nodeParseArgs({
    options: optionSpec,
    strict: true,
    allowPositionals: false,
  });
  return values;
}

export function runWrangler(args) {
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

export function sqlValue(value) {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "number") return String(value);
  return "'" + String(value).replace(/'/g, "''") + "'";
}

export function fail(message) {
  console.error(`error: ${message}`);
  process.exit(1);
}
