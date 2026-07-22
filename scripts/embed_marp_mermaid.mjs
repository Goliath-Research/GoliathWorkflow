#!/usr/bin/env node
/**
 * Post-process Marp HTML so ```mermaid fences render, then optionally print PDF.
 *
 * Usage:
 *   node scripts/embed_marp_mermaid.mjs <deck.html> [--pdf <deck.pdf>]
 */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

function npmGlobalRoot() {
  return execSync("npm root -g", { encoding: "utf8" }).trim();
}

function findMermaidMinJs() {
  const candidates = [
    resolve(npmGlobalRoot(), "mermaid/dist/mermaid.min.js"),
    resolve(__dirname, "../node_modules/mermaid/dist/mermaid.min.js"),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  throw new Error(
    "mermaid.min.js not found. Install globally: npm install -g mermaid",
  );
}

function findChromium() {
  const env = process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH;
  if (env && existsSync(env)) return env;
  for (const bin of [
    "chromium-browser",
    "chromium",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
  ]) {
    try {
      const p = execSync(`command -v ${bin}`, { encoding: "utf8" }).trim();
      if (p) return p;
    } catch {
      /* continue */
    }
  }
  throw new Error("No Chromium/Chrome executable found for PDF printing");
}

const MARKER_START = "<!-- mp-marp-mermaid-start -->";
const MARKER_END = "<!-- mp-marp-mermaid-end -->";

function stripExistingMermaidInjection(html) {
  const re = new RegExp(
    `${MARKER_START}[\\s\\S]*?${MARKER_END}\\s*`,
    "m",
  );
  return html.replace(re, "");
}

function buildInjection() {
  const b64 = readFileSync(findMermaidMinJs()).toString("base64");
  // data: URL avoids </script> breakout from the minified bundle body.
  return `${MARKER_START}
<script>
window.__MP_MERMAID_CONFIG__ = { startOnLoad: false, securityLevel: "loose" };
</script>
<script src="data:text/javascript;base64,${b64}"></script>
<script>
(async function () {
  if (!window.mermaid) return;
  mermaid.initialize(window.__MP_MERMAID_CONFIG__ || { startOnLoad: false, securityLevel: "loose" });
  // Marp may upgrade <pre is="marp-pre"> into a <marp-pre> custom element.
  const blocks = document.querySelectorAll("code.language-mermaid");
  blocks.forEach((code) => {
    const host = code.closest("pre, marp-pre") || code.parentElement;
    if (!host) return;
    const div = document.createElement("div");
    div.className = "mermaid";
    div.textContent = code.textContent;
    host.replaceWith(div);
  });
  await mermaid.run({ querySelector: ".mermaid" });
  document.documentElement.dataset.mpMermaidReady = "1";
})();
</script>
${MARKER_END}
`;
}

function embedMermaid(htmlPath) {
  let html = readFileSync(htmlPath, "utf8");
  html = stripExistingMermaidInjection(html);
  // Also strip legacy injection from older decks if re-rendered.
  html = html.replace(
    /\n?<script>\s*window\.__MP_MERMAID_CONFIG__[\s\S]*?mermaid\.run\([\s\S]*?<\/script>\s*/m,
    "\n",
  );
  if (!html.includes("language-mermaid")) {
    writeFileSync(htmlPath, html);
    return { injected: false, hasMermaid: false };
  }
  if (!html.includes("</body>")) {
    throw new Error(`${htmlPath}: missing </body>`);
  }
  html = html.replace("</body>", `${buildInjection()}\n</body>`);
  writeFileSync(htmlPath, html);
  return { injected: true, hasMermaid: true };
}

async function printPdf(htmlPath, pdfPath, { expectMermaid = true } = {}) {
  const marpCliRoot = resolve(npmGlobalRoot(), "@marp-team/marp-cli");
  const puppeteer = require(
    require.resolve("puppeteer-core", { paths: [marpCliRoot] }),
  );
  const browser = await puppeteer.launch({
    executablePath: findChromium(),
    headless: true,
    args: ["--no-sandbox", "--disable-gpu", "--allow-file-access-from-files"],
  });
  try {
    const page = await browser.newPage();
    page.on("pageerror", (err) => console.error("pageerror:", err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") console.error("console:", msg.text());
    });
    await page.setViewport({ width: 1280, height: 720, deviceScaleFactor: 1 });
    const url = pathToFileURL(resolve(htmlPath)).href;
    await page.goto(url, { waitUntil: "networkidle0", timeout: 120000 });
    if (expectMermaid) {
      await page.waitForFunction(
        () => document.documentElement.dataset.mpMermaidReady === "1",
        { timeout: 120000 },
      );
      const stats = await page.evaluate(() => ({
        pending: document.querySelectorAll("code.language-mermaid").length,
        mermaidDivs: document.querySelectorAll("div.mermaid").length,
        svgs: document.querySelectorAll("div.mermaid svg").length,
        sections: document.querySelectorAll("section").length,
      }));
      console.log("Mermaid render stats:", JSON.stringify(stats));
      if (
        stats.pending > 0 ||
        stats.mermaidDivs === 0 ||
        stats.svgs < stats.mermaidDivs
      ) {
        throw new Error(`Mermaid did not fully render: ${JSON.stringify(stats)}`);
      }
      await new Promise((r) => setTimeout(r, 300));
    }
    // Marp bare template uses one SVG wrapper per slide; print with CSS page size.
    await page.pdf({
      path: pdfPath,
      width: "1280px",
      height: "720px",
      printBackground: true,
      preferCSSPageSize: true,
    });
  } finally {
    await browser.close();
  }
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.error(
      "Usage: node scripts/embed_marp_mermaid.mjs <deck.html> [--pdf <deck.pdf>]",
    );
    process.exit(2);
  }
  const htmlPath = resolve(args[0]);
  let pdfPath = null;
  const pdfIdx = args.indexOf("--pdf");
  if (pdfIdx >= 0) {
    pdfPath = resolve(args[pdfIdx + 1] || htmlPath.replace(/\.html$/i, ".pdf"));
  }

  const { injected, hasMermaid } = embedMermaid(htmlPath);
  console.log(
    injected
      ? `Embedded Mermaid runtime into ${htmlPath}`
      : `No Mermaid fences in ${htmlPath}; left unchanged`,
  );

  if (pdfPath) {
    await printPdf(htmlPath, pdfPath, { expectMermaid: !!hasMermaid });
    console.log(`Wrote PDF ${pdfPath}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
