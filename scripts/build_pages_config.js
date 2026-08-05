"use strict";

const fs = require("node:fs");

/** Build the public runtime config injected into the GitHub Pages artifact. */
function renderConfig(rawValue) {
  const rawBase = String(rawValue || "").trim();
  let parsed;

  try {
    parsed = new URL(rawBase);
  } catch {
    throw new Error("AIMS_API_BASE must be a complete HTTPS URL");
  }

  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error(
      "AIMS_API_BASE must be an HTTPS origin without credentials, a path, a query, or a fragment",
    );
  }

  return [
    '"use strict";',
    "",
    "// Generated during the GitHub Pages deployment. This URL is public.",
    `window.AIMS_API_BASE = ${JSON.stringify(parsed.origin)};`,
    "",
  ].join("\n");
}

if (require.main === module) {
  const outputPath = process.argv[2];
  if (!outputPath) {
    throw new Error("Usage: node scripts/build_pages_config.js <output-path>");
  }
  fs.writeFileSync(outputPath, renderConfig(process.env.AIMS_API_BASE), "utf8");
}

module.exports = { renderConfig };
