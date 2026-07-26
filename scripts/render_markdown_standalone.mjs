#!/usr/bin/env node
/**
 * Render a Markdown article to a self-contained HTML file with Mermaid diagrams.
 *
 * Mermaid is embedded from the local/global mermaid package so the HTML works
 * offline via file://. Relative .md/.qmd links stay as-is for repo readers.
 *
 * Usage:
 *   node scripts/render_markdown_standalone.mjs <input.md> [-o <output.html>]
 *   node scripts/render_markdown_standalone.mjs --regulatory
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve, basename, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { marked } from "marked";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const require = createRequire(import.meta.url);

function npmGlobalRoot() {
  return execSync("npm root -g", { encoding: "utf8" }).trim();
}

function findMermaidMinJs() {
  const candidates = [
    resolve(ROOT, "node_modules/mermaid/dist/mermaid.min.js"),
    resolve(npmGlobalRoot(), "mermaid/dist/mermaid.min.js"),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  throw new Error(
    "mermaid.min.js not found. Install: npm install mermaid (repo or -g)",
  );
}

function parseArgs(argv) {
  const args = argv.slice(2);
  if (args.includes("--regulatory") || args.includes("-r")) {
    const input = resolve(
      ROOT,
      "docs/regulatory/Regulatory-Ready Platform for Multiomics Diagnostics.md",
    );
    const output = resolve(
      ROOT,
      "docs/regulatory/Regulatory-Ready Platform for Multiomics Diagnostics.html",
    );
    return { input, output };
  }
  const input = args.find((a) => !a.startsWith("-") && a !== "-o");
  const oIdx = args.indexOf("-o");
  const output =
    oIdx >= 0
      ? resolve(args[oIdx + 1])
      : input
        ? resolve(
            dirname(resolve(input)),
            basename(resolve(input), extname(resolve(input))) + ".html",
          )
        : null;
  if (!input || !output) {
    console.error(
      "Usage: node scripts/render_markdown_standalone.mjs <input.md> [-o out.html]\n" +
        "       node scripts/render_markdown_standalone.mjs --regulatory",
    );
    process.exit(1);
  }
  return { input: resolve(input), output };
}

function extractTitle(md) {
  const m = md.match(/^#\s+(.+)$/m);
  return m ? m[1].trim() : "Document";
}

/** Turn fenced ```mermaid into <pre class="mermaid"> for client render. */
function preprocessMermaid(md) {
  return md.replace(/```mermaid\n([\s\S]*?)```/g, (_all, body) => {
    const escaped = String(body)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return `<pre class="mermaid">${escaped}</pre>\n`;
  });
}

function buildHtml({ title, bodyHtml, mermaidJs }) {
  const generated = new Date().toISOString().slice(0, 10);
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>${title.replace(/</g, "&lt;")}</title>
<style>
  :root {
    --ink: #0f172a;
    --muted: #475569;
    --soft: #64748b;
    --line: #e2e8f0;
    --paper: #f8fafc;
    --card: #ffffff;
    --teal: #0d9488;
    --teal-deep: #0f766e;
    --sky: #0369a1;
    --amber: #d97706;
    --code-bg: #0f172a;
    --code-fg: #e2e8f0;
    --quote-bg: #ecfeff;
    --quote-border: #0d9488;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    color: var(--ink);
    font-family: "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
    line-height: 1.65;
    background:
      radial-gradient(1100px 520px at 100% -8%, rgba(3, 105, 161, 0.12), transparent 55%),
      radial-gradient(900px 480px at -8% 100%, rgba(13, 148, 136, 0.14), transparent 50%),
      var(--paper);
  }
  .banner {
    background: linear-gradient(120deg, #0f766e 0%, #0369a1 58%, #0ea5e9 100%);
    color: #f8fafc;
    padding: 2.75rem 1.5rem 2.25rem;
  }
  .banner-inner, .wrap {
    max-width: 48rem;
    margin: 0 auto;
  }
  .banner .kicker {
    letter-spacing: 0.12em;
    text-transform: uppercase;
    font-size: 0.75rem;
    font-weight: 700;
    opacity: 0.9;
    margin: 0 0 0.75rem;
  }
  .banner h1 {
    margin: 0;
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, serif;
    font-weight: 700;
    font-size: clamp(1.75rem, 4vw, 2.45rem);
    line-height: 1.2;
    letter-spacing: -0.02em;
  }
  .banner .meta {
    margin: 1rem 0 0;
    font-size: 0.9rem;
    opacity: 0.88;
  }
  .wrap {
    padding: 2rem 1.5rem 4rem;
  }
  article > h1 { display: none; }
  h2, h3, h4 {
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, serif;
    letter-spacing: -0.015em;
    line-height: 1.25;
    color: var(--ink);
  }
  h2 {
    margin: 2.5rem 0 1rem;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid var(--teal);
    font-size: 1.55rem;
  }
  h3 { margin: 1.75rem 0 0.75rem; font-size: 1.2rem; color: var(--teal-deep); }
  h4 { margin: 1.4rem 0 0.6rem; font-size: 1.05rem; }
  p, li { font-size: 1.02rem; }
  a { color: var(--sky); text-underline-offset: 2px; }
  a:hover { color: var(--teal-deep); }
  hr {
    border: 0;
    border-top: 1px solid var(--line);
    margin: 2.25rem 0;
  }
  blockquote {
    margin: 1.25rem 0;
    padding: 0.9rem 1.1rem;
    background: var(--quote-bg);
    border-left: 4px solid var(--quote-border);
    color: var(--muted);
    border-radius: 0 0.5rem 0.5rem 0;
  }
  blockquote p { margin: 0.35rem 0; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.25rem 0 1.75rem;
    font-size: 0.95rem;
    background: var(--card);
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    border-radius: 0.5rem;
    overflow: hidden;
  }
  th, td {
    border: 1px solid var(--line);
    padding: 0.65rem 0.75rem;
    text-align: left;
    vertical-align: top;
  }
  th {
    background: #f1f5f9;
    font-weight: 700;
    color: var(--ink);
  }
  tr:nth-child(even) td { background: #fbfdff; }
  code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.88em;
    background: #e2e8f0;
    padding: 0.12em 0.35em;
    border-radius: 0.3em;
  }
  pre {
    background: var(--code-bg);
    color: var(--code-fg);
    padding: 1rem 1.1rem;
    border-radius: 0.65rem;
    overflow-x: auto;
    font-size: 0.88rem;
    line-height: 1.45;
  }
  pre code { background: transparent; color: inherit; padding: 0; }
  pre.mermaid {
    background: var(--card);
    color: var(--ink);
    border: 1px solid var(--line);
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    padding: 1.25rem;
    text-align: center;
    overflow-x: auto;
  }
  pre.mermaid svg { max-width: 100%; height: auto; }
  .footer-note {
    margin-top: 3rem;
    padding-top: 1rem;
    border-top: 1px solid var(--line);
    color: var(--soft);
    font-size: 0.85rem;
  }
  @media print {
    body { background: #fff; }
    .banner { background: #0f766e !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    a { color: inherit; text-decoration: none; }
    pre.mermaid { box-shadow: none; break-inside: avoid; }
  }
</style>
</head>
<body>
  <header class="banner">
    <div class="banner-inner">
      <p class="kicker">MethylPipeline · Regulatory strategy</p>
      <h1>${title.replace(/</g, "&lt;")}</h1>
      <p class="meta">Standalone HTML · Mermaid diagrams render in-browser · Generated ${generated}</p>
    </div>
  </header>
  <main class="wrap">
    <article>
${bodyHtml}
    </article>
    <p class="footer-note">
      Source: docs/regulatory markdown in the MethylPipeline repository.
      Claim boundary: architecture and filled feasibility packages are not FDA clearance or approval.
    </p>
  </main>
  <script>${mermaidJs}</script>
  <script>
    mermaid.initialize({
      startOnLoad: true,
      securityLevel: "loose",
      theme: "base",
      themeVariables: {
        primaryColor: "#ccfbf1",
        primaryTextColor: "#0f172a",
        primaryBorderColor: "#0d9488",
        lineColor: "#0369a1",
        secondaryColor: "#e0f2fe",
        tertiaryColor: "#f8fafc",
        fontFamily: "Segoe UI, Helvetica Neue, Helvetica, Arial, sans-serif"
      },
      flowchart: { curve: "basis", padding: 16 }
    });
  </script>
</body>
</html>
`;
}

const { input, output } = parseArgs(process.argv);
if (!existsSync(input)) {
  console.error(`Input not found: ${input}`);
  process.exit(1);
}

const md = readFileSync(input, "utf8");
const title = extractTitle(md);
const prepared = preprocessMermaid(md);
const bodyHtml = marked.parse(prepared, { async: false });
const mermaidJs = readFileSync(findMermaidMinJs(), "utf8");
const html = buildHtml({ title, bodyHtml, mermaidJs });

mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, html, "utf8");
const kb = Math.round(Buffer.byteLength(html) / 1024);
console.log(`Wrote ${output} (${kb} KiB)`);
