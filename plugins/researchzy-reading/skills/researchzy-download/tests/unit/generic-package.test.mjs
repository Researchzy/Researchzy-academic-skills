import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const runtimeRoots = ["SKILL.md", "manifest.yaml", "agents", "data", "references", "scripts"];
const textExtensions = new Set([".md", ".yaml", ".yml", ".json", ".py", ".mjs", ".txt"]);

function filesUnder(relative) {
  const target = path.join(root, relative);
  if (!fs.existsSync(target)) return [];
  if (fs.statSync(target).isFile()) return [target];
  return fs.readdirSync(target, { withFileTypes: true }).flatMap((entry) =>
    entry.name === "__pycache__" ? [] : filesUnder(path.join(relative, entry.name))
  );
}

const files = runtimeRoots.flatMap(filesUnder).filter((file) => textExtensions.has(path.extname(file)));
const joined = files.map((file) => `${path.relative(root, file)}\n${fs.readFileSync(file, "utf8")}`).join("\n");

test("distributed skill contains no local identity or secret file", () => {
  assert.doesNotMatch(joined, /\/Users\/[a-z0-9._-]+\/|C:\\Users\\[a-z0-9._-]+\\/i);
  for (const forbidden of ["credentials.json", "settings.json", ".env"]) {
    assert.equal(files.some((file) => path.basename(file) === forbidden), false, `${forbidden} must not be distributed`);
  }
});

test("the skill is English-only and has no browser or CNKI route", () => {
  assert.doesNotMatch(joined, /[\u3400-\u9fff\uf900-\ufaff]/u);
  assert.doesNotMatch(joined, /cnki|\bcaj\b|carsi|anti-bot|cdp-utils|webofscience/i);
});
