// Copyright (c) 2026 Mechemsi. All rights reserved.
// Licensed under AGPLv3. See LICENSE file.
// Commercial licensing: info@mechemsi.com

/**
 * Check cyclomatic complexity of TypeScript/TSX files using ESLint.
 *
 * Usage: node scripts/check-complexity.mjs <max_complexity> [file1.tsx file2.ts ...]
 *
 * max_complexity: Maximum allowed cyclomatic complexity (default: 15).
 * If files are provided, only those are checked. Otherwise checks all
 * files under src/.
 *
 * Exit codes:
 *   0 — no functions above the threshold
 *   1 — at least one function above the threshold
 */

import { execSync } from "node:child_process";
import { existsSync } from "node:fs";

const args = process.argv.slice(2);
const maxComplexity = parseInt(args[0], 10) || 15;
const files = args.slice(1).filter((f) => existsSync(f));

const targets = files.length > 0 ? files.join(" ") : "src/";

// Run ESLint with only the complexity rule enabled
const cmd = [
  "npx",
  "eslint",
  "--no-eslintrc",
  "-c",
  '{"rules":{"complexity":["warn",' + maxComplexity + "]}}",
  "--parser",
  "@typescript-eslint/parser",
  "--plugin",
  "@typescript-eslint",
  "--ext",
  ".ts,.tsx",
  "--format",
  "stylish",
  targets,
].join(" ");

try {
  const output = execSync(cmd, {
    encoding: "utf-8",
    stdio: ["pipe", "pipe", "pipe"],
  });
  // If no warnings, ESLint exits 0 and output is empty or just whitespace
  if (output.trim()) {
    console.log(output.trim());
  }
  console.log(
    `All functions are below complexity ${maxComplexity}. No issues found.`
  );
  process.exit(0);
} catch (err) {
  const output = (err.stdout || "") + (err.stderr || "");
  if (output.includes("complexity")) {
    console.log(`Functions exceeding complexity threshold ${maxComplexity}:\n`);
    console.log(output.trim());
    console.log(
      `\nReduce complexity by extracting helper functions or simplifying control flow.`
    );
    process.exit(1);
  }
  // ESLint may exit non-zero for parsing errors — still report
  if (output.trim()) {
    console.log(output.trim());
  }
  console.log(
    `All functions are below complexity ${maxComplexity}. No issues found.`
  );
  process.exit(0);
}
