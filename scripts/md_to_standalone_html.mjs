#!/usr/bin/env node
/**
 * Convert a Markdown doc into one self-contained HTML file that is small enough
 * to email as an attachment. Mermaid fences stay as Mermaid source and are
 * rendered in the browser by the Mermaid ESM bundle loaded from a CDN.
 *
 * Usage:
 *   node scripts/md_to_standalone_html.mjs <input.md> [output.html] [--title "..."]
 *
 * Markdown is converted with the `marked` CLI via npx (no repo dependency).
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, resolve } from "node:path";
import { tmpdir } from "node:os";

const MERMAID_ESM =
  "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";

const USAGE =
  "Usage: node scripts/md_to_standalone_html.mjs <input.md> [output.html] [--title <title>]";

function parseArgs(argv) {
  const positional = [];
  let title = null;
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === "--title") {
      const value = argv[i + 1];
      if (value === undefined || value.startsWith("-")) {
        throw new Error(`${USAGE}\n--title requires a value`);
      }
      title = value;
      i += 1;
    } else {
      positional.push(argv[i]);
    }
  }
  if (positional.length < 1) {
    throw new Error(USAGE);
  }
  const input = resolve(positional[0]);
  const output = positional[1]
    ? resolve(positional[1])
    : input.replace(/\.md$/i, "") + ".html";
  return { input, output, title };
}

function markdownToHtml(input) {
  const tmp = mkdtempSync(resolve(tmpdir(), "md2html-"));
  const bodyPath = resolve(tmp, "body.html");
  try {
    // Resolve `npx` from PATH. Windows Node cannot spawn `.cmd` shims without a
    // shell (EINVAL); argv is still passed as an array, not a concatenated string.
    execFileSync(
      "npx",
      ["--yes", "marked", "--gfm", "-i", input, "-o", bodyPath],
      {
        stdio: ["ignore", "ignore", "inherit"],
        windowsHide: true,
        shell: process.platform === "win32",
      },
    );
    return readFileSync(bodyPath, "utf8");
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Mermaid reads element textContent, so escaped entities decode correctly. */
function unwrapMermaidFences(html) {
  let count = 0;
  const out = html.replace(
    /<pre><code class="language-mermaid">([\s\S]*?)<\/code><\/pre>/g,
    (_match, source) => {
      count += 1;
      return `<pre class="mermaid">${source}</pre>`;
    },
  );
  return { html: out, count };
}

function firstHeading(html, fallback) {
  const match = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/);
  if (!match) return fallback;
  return match[1].replace(/<[^>]+>/g, "").trim() || fallback;
}

function documentShell({ title, body }) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
<style>
  :root {
    --ink: #0f172a;
    --muted: #475569;
    --line: #e2e8f0;
    --accent: #0f766e;
    --accent-soft: #f0fdfa;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0 auto;
    max-width: 62rem;
    padding: 2.5rem 1.5rem 4rem;
    color: var(--ink);
    background: #fff;
    font: 16px/1.62 "Segoe UI", -apple-system, "Helvetica Neue", Arial, sans-serif;
  }
  h1, h2, h3, h4 { line-height: 1.25; margin: 2.2rem 0 0.8rem; }
  h1 { font-size: 1.95rem; margin-top: 0; }
  h2 { font-size: 1.45rem; padding-bottom: 0.3rem; border-bottom: 2px solid var(--line); }
  h3 { font-size: 1.15rem; }
  p, li { margin: 0.55rem 0; }
  a { color: var(--accent); }
  hr { border: none; border-top: 1px solid var(--line); margin: 2.4rem 0; }
  strong { color: #0b1220; }
  code {
    font-family: "Cascadia Mono", Consolas, monospace;
    font-size: 0.88em;
    background: var(--accent-soft);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 0.05rem 0.3rem;
  }
  pre {
    background: #f8fafc;
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 0.9rem 1rem;
    overflow-x: auto;
  }
  pre code { background: none; border: none; padding: 0; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.2rem 0;
    font-size: 0.93rem;
  }
  th, td { border: 1px solid var(--line); padding: 0.5rem 0.65rem; text-align: left; vertical-align: top; }
  th { background: var(--accent-soft); }
  blockquote {
    margin: 1.2rem 0;
    padding: 0.2rem 1rem;
    border-left: 3px solid var(--accent);
    color: var(--muted);
  }
  pre.mermaid {
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1rem;
    text-align: center;
    overflow-x: auto;
  }
  pre.mermaid svg { max-width: 100%; height: auto; }
  .mermaid-offline-note {
    display: none;
    margin: 1.2rem 0;
    padding: 0.7rem 1rem;
    border: 1px dashed var(--accent);
    border-radius: 8px;
    background: var(--accent-soft);
    color: var(--muted);
    font-size: 0.9rem;
  }
  .mermaid-offline-note.show { display: block; }
  @media print {
    body { max-width: none; padding: 0; }
    .mermaid-offline-note { display: none !important; }
  }
</style>
</head>
<body>
<p class="mermaid-offline-note" id="mermaid-offline-note">
  Diagrams need a network connection: Mermaid is loaded from a CDN. The diagram
  source below each heading stays readable as plain text when offline.
</p>
${body}
<script type="module">
  import mermaid from "${MERMAID_ESM}";
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose",
    theme: "base",
    themeVariables: {
      darkMode: false,
      background: "#ffffff",
      fontFamily: "Segoe UI, Helvetica Neue, Arial, sans-serif",
      primaryColor: "#ccfbf1",
      primaryTextColor: "#0f172a",
      primaryBorderColor: "#0f766e",
      lineColor: "#334155",
      textColor: "#0f172a",
      clusterBkg: "#f0fdfa",
      clusterBorder: "#0d9488",
      edgeLabelBackground: "#ffffff"
    }
  });
  await mermaid.run({ querySelector: "pre.mermaid" });
</script>
<script>
  // CDN blocked or offline: keep the page usable and say why.
  window.addEventListener("load", () => {
    if (!document.querySelector("pre.mermaid svg")) {
      document.getElementById("mermaid-offline-note")?.classList.add("show");
    }
  });
</script>
</body>
</html>
`;
}

const { input, output, title } = parseArgs(process.argv.slice(2));
const rendered = markdownToHtml(input);
const { html: body, count } = unwrapMermaidFences(rendered);
const docTitle = title ?? firstHeading(body, basename(input, ".md"));
writeFileSync(output, documentShell({ title: docTitle, body }), "utf8");
console.log(`${output} (${count} mermaid diagram${count === 1 ? "" : "s"})`);
