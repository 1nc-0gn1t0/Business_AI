// Redocly 1.x expects minimatch's pre-v9 callable CommonJS export. Use the
// patched upstream engine's public named export without changing the generator.
// Remove this compatibility patch when openapi-typescript upgrades Redocly.
const { createRequire } = require("node:module");
const { readFileSync, writeFileSync } = require("node:fs");
const assert = require("node:assert/strict");
const fromGenerator = createRequire(require.resolve("openapi-typescript"));
const version = fromGenerator("@redocly/openapi-core/package.json").version;
if (version !== "1.34.22") {
  throw new Error("Review Redocly minimatch compatibility for the new version");
}
const target = fromGenerator.resolve("@redocly/openapi-core/lib/utils.js");
const before = 'const minimatch = require("minimatch");';
const after = 'const minimatch = require("minimatch").minimatch;';
const source = readFileSync(target, "utf8");
if (!(source.includes(after) && !source.includes(before))) {
  if (source.split(before).length !== 2) {
    throw new Error("Unexpected Redocly source; compatibility patch was not applied");
  }
  writeFileSync(target, source.replace(before, after));
}
// Exercise the affected resolver path, not just module loading/type generation.
const { readFileFromUrl } = fromGenerator("@redocly/openapi-core/lib/utils.js");
Promise.all([
  ["https://example.org/api/a.json", "example.org/api/*.json", true],
  ["https://other.org/api/a.json", "example.org/api/*.json", false],
  ["https://example.org/api/a.json", "http://example.org/**", false],
].map(([url, pattern, matches]) => readFileFromUrl(url, {
  headers: [{ name: "X-Test", value: "synthetic", matches: pattern }],
  customFetch: async (_url, options) => {
    assert.deepEqual(options.headers, matches ? { "X-Test": "synthetic" } : {});
    return { ok: true, text: async () => "{}", headers: { get: () => "application/json" } };
  },
}))).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
