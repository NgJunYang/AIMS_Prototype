"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");

const { renderConfig } = require("../scripts/build_pages_config.js");

test("Pages config contains the normalized public backend origin", () => {
  const rendered = renderConfig(" https://example-backend.onrender.com/ ");

  assert.match(
    rendered,
    /window\.AIMS_API_BASE = "https:\/\/example-backend\.onrender\.com";/,
  );
});

test("Pages config rejects missing, insecure, or non-origin URLs", () => {
  const invalidValues = [
    "",
    "http://example.com",
    "https://user:pass@example.com",
    "https://example.com/api",
    "https://example.com?q=1",
    "https://example.com/#fragment",
  ];

  for (const value of invalidValues) {
    assert.throws(() => renderConfig(value), /AIMS_API_BASE/);
  }
});

test("local frontend assets use repository-subpath-safe URLs", () => {
  const html = fs.readFileSync("static/index.html", "utf8");

  for (const asset of ["./app.css", "./config.js", "./app.js"]) {
    assert.ok(html.includes(asset), `missing relative asset reference: ${asset}`);
  }
  assert.doesNotMatch(html, /\b(?:href|src)="\//);
});

test("committed runtime config keeps local development same-origin", () => {
  const config = fs.readFileSync("static/config.js", "utf8");
  assert.match(config, /window\.AIMS_API_BASE = "";/);
});
