#!/usr/bin/env node
/**
 * Enforce baseline Inngest reliability policy on touched function files:
 * - Explicit retries per createFunction
 * - Explicit concurrency per createFunction
 * - DB-touching files must include DB_CONCURRENCY in createFunction options
 * - Files that call fetch() must include an explicit timeout mechanism
 */

const fs = require("fs");
const path = require("path");

function listAllInngestFiles() {
  const dir = path.join("frontend", "src", "inngest");
  if (!fs.existsSync(dir)) {
    return [];
  }
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith(".ts"))
    .map((name) => path.join(dir, name));
}

function lineFromIndex(text, index) {
  return text.slice(0, index).split("\n").length;
}

function isDbTouching(text) {
  return (
    /\bdbPool\b/.test(text) ||
    /\bpool\.connect\s*\(/.test(text) ||
    /\bclient\.query\s*\(/.test(text) ||
    /from\s+["']@\/lib\/db["']/.test(text) ||
    /from\s+["']pg["']/.test(text)
  );
}

function hasFetchTimeoutPolicy(text) {
  // Accept either AbortSignal.timeout(...) or AbortController + controller.abort()
  return (
    /AbortSignal\.timeout\s*\(/.test(text) ||
    /controller\.abort\s*\(/.test(text)
  );
}

function checkFile(filePath) {
  const src = fs.readFileSync(filePath, "utf8");
  const violations = [];

  const dbTouching = isDbTouching(src);
  const createFnRegex = /createFunction\(\s*\{([\s\S]*?)\}\s*,\s*\{([\s\S]*?)\}\s*,/g;

  let match;
  while ((match = createFnRegex.exec(src)) !== null) {
    const options = match[1];
    const line = lineFromIndex(src, match.index);

    const hasRetries = /\bretries\s*:/.test(options);
    const hasConcurrency = /\bconcurrency\s*:/.test(options);
    const hasDbConcurrency = /\bDB_CONCURRENCY\b/.test(options);

    if (!hasRetries) {
      violations.push(`${filePath}:${line} missing retries in createFunction options`);
    }
    if (!hasConcurrency) {
      violations.push(`${filePath}:${line} missing concurrency in createFunction options`);
    }
    if (dbTouching && !hasDbConcurrency) {
      violations.push(
        `${filePath}:${line} DB-touching function missing DB_CONCURRENCY in createFunction options`,
      );
    }
  }

  if (/\bfetch\s*\(/.test(src) && !hasFetchTimeoutPolicy(src)) {
    violations.push(
      `${filePath}:1 fetch() found without explicit timeout policy (AbortSignal.timeout or controller.abort)`,
    );
  }

  return violations;
}

function main() {
  const args = process.argv.slice(2);
  const files = (args.length > 0 ? args : listAllInngestFiles()).filter((f) =>
    f.startsWith(path.join("frontend", "src", "inngest")),
  );

  if (files.length === 0) {
    process.exit(0);
  }

  const allViolations = [];
  for (const filePath of files) {
    if (!fs.existsSync(filePath)) {
      continue;
    }
    const fileViolations = checkFile(filePath);
    allViolations.push(...fileViolations);
  }

  if (allViolations.length > 0) {
    console.error("Inngest policy check failed:");
    for (const violation of allViolations) {
      console.error(`- ${violation}`);
    }
    process.exit(1);
  }
}

main();
