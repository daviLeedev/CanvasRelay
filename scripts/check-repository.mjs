import { execFileSync } from "node:child_process";
import { readFileSync, statSync } from "node:fs";
import { basename, extname } from "node:path";

const trackedOutput = execFileSync("git", ["ls-files"], { encoding: "utf8" }).trim();
const trackedFiles = trackedOutput ? trackedOutput.split(/\r?\n/u) : [];
const blockedNames = new Set([".env", ".env.local", ".env.production", ".env.development"]);
const blockedExtensions = new Set([".log", ".safetensors", ".ckpt", ".gguf", ".pt", ".pth"]);
const maxFileBytes = 5 * 1024 * 1024;
const windowsProfilePattern = new RegExp(String.raw`[A-Za-z]:\\Users\\[^\\/\s]+`, "u");
const unixProfilePattern = new RegExp(String.raw`/(Users|home)/[^/\s]+`, "u");
const violations = [];

for (const file of trackedFiles) {
  const fileName = basename(file);
  const extension = extname(fileName).toLowerCase();
  const stats = statSync(file);

  if (blockedNames.has(fileName) || blockedExtensions.has(extension)) {
    violations.push(`${file}: disallowed tracked file`);
  }

  if (stats.size > maxFileBytes) {
    violations.push(`${file}: exceeds the ${maxFileBytes} byte repository limit`);
  }

  if (stats.size <= 1024 * 1024) {
    const buffer = readFileSync(file);
    if (!buffer.includes(0)) {
      const text = buffer.toString("utf8");
      if (windowsProfilePattern.test(text) || unixProfilePattern.test(text)) {
        violations.push(`${file}: contains a personal absolute path`);
      }
    }
  }
}

if (violations.length > 0) {
  console.error(violations.join("\n"));
  process.exit(1);
}

console.log(`Repository policy passed for ${trackedFiles.length} tracked files.`);
