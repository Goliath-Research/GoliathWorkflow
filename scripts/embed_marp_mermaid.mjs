#!/usr/bin/env node
/**
 * Post-process Marp HTML so ```mermaid fences render, then optionally print PDF.
 *
 * Adds a dynamic Mermaid control (pan / zoom / fit / expand) for diagrams that
 * overflow the slide, so sales decks stay interactive without clipping.
 *
 * Usage:
 *   node scripts/embed_marp_mermaid.mjs <deck.html> [--pdf <deck.pdf>]
 *
 * Authoring tip: put `%% mp:interactive` on the first line of a Mermaid fence to
 * force controls even when the diagram fits.
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
  const re = new RegExp(`${MARKER_START}[\\s\\S]*?${MARKER_END}\\s*`, "m");
  return html.replace(re, "");
}

function buildInjection() {
  const b64 = readFileSync(findMermaidMinJs()).toString("base64");
  // data: URL avoids </script> breakout from the minified bundle body.
  return `${MARKER_START}
<style id="mp-mermaid-controls-css">
.mp-mermaid-shell {
  position: relative;
  width: 100%;
  max-width: 100%;
  border: 1px solid #99f6e4;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f0fdfa 100%);
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}
.mp-mermaid-toolbar {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: flex-end;
  padding: 6px 8px;
  background: rgba(15, 118, 110, 0.08);
  border-bottom: 1px solid #99f6e4;
  font-size: 12px;
  z-index: 2;
}
.mp-mermaid-toolbar button {
  appearance: none;
  border: 1px solid #0f766e;
  background: #0f766e;
  color: #f8fafc;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  line-height: 1.4;
}
.mp-mermaid-toolbar button:hover { background: #0d9488; }
.mp-mermaid-toolbar .mp-mermaid-hint {
  margin-right: auto;
  color: #0f766e;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.mp-mermaid-viewport {
  position: relative;
  width: 100%;
  height: 420px;
  overflow: hidden;
  cursor: grab;
  touch-action: none;
  background: #fff;
}
.mp-mermaid-viewport.is-dragging { cursor: grabbing; }
.mp-mermaid-viewport .mermaid {
  position: absolute;
  inset: 0;
  margin: 0 !important;
  width: 100%;
  height: 100%;
  display: block;
  background: transparent !important;
  border: none !important;
}
.mp-mermaid-viewport .mermaid svg {
  max-width: none !important;
  height: auto !important;
  transform-origin: 0 0;
  display: block;
}
.mp-mermaid-lightbox {
  position: fixed;
  inset: 0;
  z-index: 99999;
  display: none;
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(2px);
  padding: 28px;
  box-sizing: border-box;
}
.mp-mermaid-lightbox.open { display: flex; flex-direction: column; }
.mp-mermaid-lightbox .mp-mermaid-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
}
.mp-mermaid-lightbox .mp-mermaid-viewport {
  flex: 1;
  height: auto;
  min-height: 0;
}
@media print {
  .mp-mermaid-toolbar, .mp-mermaid-lightbox { display: none !important; }
  .mp-mermaid-shell { border: none; box-shadow: none; background: transparent; }
  .mp-mermaid-viewport { height: auto !important; overflow: visible !important; cursor: default; }
  .mp-mermaid-viewport .mermaid { position: static; }
  .mp-mermaid-viewport .mermaid svg { max-width: 100% !important; transform: none !important; }
}
</style>
<script>
window.__MP_MERMAID_CONFIG__ = {
  startOnLoad: false,
  securityLevel: "loose",
  theme: "base",
  themeVariables: {
    darkMode: false,
    background: "#ffffff",
    fontFamily: "Segoe UI, Helvetica Neue, Arial, sans-serif",
    primaryColor: "#99f6e4",
    primaryTextColor: "#0f172a",
    primaryBorderColor: "#0f766e",
    secondaryColor: "#fde68a",
    tertiaryColor: "#e0f2fe",
    lineColor: "#334155",
    textColor: "#0f172a",
    mainBkg: "#ccfbf1",
    nodeBorder: "#0f766e",
    clusterBkg: "#f0fdfa",
    clusterBorder: "#0d9488",
    titleColor: "#0f766e",
    edgeLabelBackground: "#ffffff",
    actorBkg: "#ccfbf1",
    actorBorder: "#0f766e",
    labelBoxBkgColor: "#ecfeff",
    labelBoxBorderColor: "#0d9488",
    labelTextColor: "#0f172a"
  }
};
</script>
<script src="data:text/javascript;base64,${b64}"></script>
<script>
(async function () {
  if (!window.mermaid) return;
  mermaid.initialize(window.__MP_MERMAID_CONFIG__ || { startOnLoad: false, securityLevel: "loose" });

  const INTERACTIVE_RE = /^\\s*%%\\s*mp:interactive\\s*$/im;

  // Marp may upgrade <pre is="marp-pre"> into a <marp-pre> custom element.
  const blocks = document.querySelectorAll("code.language-mermaid");
  const sources = [];
  blocks.forEach((code) => {
    const host = code.closest("pre, marp-pre") || code.parentElement;
    if (!host) return;
    let text = code.textContent || "";
    const forceInteractive = INTERACTIVE_RE.test(text);
    if (forceInteractive) text = text.replace(INTERACTIVE_RE, "").trimStart();
    const div = document.createElement("div");
    div.className = "mermaid";
    div.textContent = text;
    if (forceInteractive) div.dataset.mpInteractive = "1";
    host.replaceWith(div);
    sources.push(div);
  });

  await mermaid.run({ querySelector: ".mermaid" });

  function svgNaturalSize(svg) {
    const vb = svg.viewBox && svg.viewBox.baseVal;
    let w = Number(svg.getAttribute("width")) || (vb && vb.width) || svg.getBBox().width;
    let h = Number(svg.getAttribute("height")) || (vb && vb.height) || svg.getBBox().height;
    // Strip units like "px"
    if (typeof w === "string") w = parseFloat(w);
    if (typeof h === "string") h = parseFloat(h);
    return { w: w || 800, h: h || 450 };
  }

  function availableViewportHeight(el) {
    const section = el.closest("section");
    if (!section) return 420;
    const sectionH = section.clientHeight || 720;
    const top = el.getBoundingClientRect().top - section.getBoundingClientRect().top;
    // Leave room for footer / page number.
    return Math.max(220, Math.min(520, sectionH - top - 70));
  }

  function enhanceDiagram(mermaidDiv) {
    const svg = mermaidDiv.querySelector("svg");
    if (!svg || mermaidDiv.closest(".mp-mermaid-shell")) return;

    const { w: natW, h: natH } = svgNaturalSize(svg);
    const targetH = availableViewportHeight(mermaidDiv);
    const targetW = Math.max(320, (mermaidDiv.parentElement?.clientWidth || 1100) - 8);
    const overflows =
      mermaidDiv.dataset.mpInteractive === "1" ||
      natH > targetH * 0.92 ||
      natW > targetW * 0.98;
    if (!overflows && mermaidDiv.dataset.mpInteractive !== "1") {
      // Still clamp max width so small diagrams stay tidy.
      svg.style.maxWidth = "100%";
      return;
    }

    const shell = document.createElement("div");
    shell.className = "mp-mermaid-shell";
    const toolbar = document.createElement("div");
    toolbar.className = "mp-mermaid-toolbar";
    toolbar.innerHTML =
      '<span class="mp-mermaid-hint">Drag · scroll to zoom</span>' +
      '<button type="button" data-act="out" title="Zoom out">−</button>' +
      '<button type="button" data-act="in" title="Zoom in">+</button>' +
      '<button type="button" data-act="fit" title="Fit">Fit</button>' +
      '<button type="button" data-act="expand" title="Expand">Expand</button>';
    const viewport = document.createElement("div");
    viewport.className = "mp-mermaid-viewport";
    viewport.style.height = targetH + "px";

    mermaidDiv.replaceWith(shell);
    shell.appendChild(toolbar);
    shell.appendChild(viewport);
    viewport.appendChild(mermaidDiv);

    svg.removeAttribute("width");
    svg.removeAttribute("height");
    svg.style.maxWidth = "none";
    svg.style.width = natW + "px";
    svg.style.height = natH + "px";

    const state = { scale: 1, x: 0, y: 0, dragging: false, lx: 0, ly: 0 };

    function apply() {
      svg.style.transform =
        "translate(" + state.x + "px," + state.y + "px) scale(" + state.scale + ")";
    }

    function fit() {
      const vw = viewport.clientWidth || targetW;
      const vh = viewport.clientHeight || targetH;
      const pad = 16;
      const s = Math.min((vw - pad) / natW, (vh - pad) / natH, 1.25);
      state.scale = Math.max(0.15, s);
      state.x = (vw - natW * state.scale) / 2;
      state.y = (vh - natH * state.scale) / 2;
      apply();
    }

    function zoomAt(factor, cx, cy) {
      const prev = state.scale;
      const next = Math.min(4, Math.max(0.15, prev * factor));
      if (next === prev) return;
      // Zoom toward cursor point inside viewport.
      const rect = viewport.getBoundingClientRect();
      const px = (cx ?? rect.left + rect.width / 2) - rect.left;
      const py = (cy ?? rect.top + rect.height / 2) - rect.top;
      state.x = px - ((px - state.x) * next) / prev;
      state.y = py - ((py - state.y) * next) / prev;
      state.scale = next;
      apply();
    }

    function stopSlideNav(ev) {
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === "function") ev.stopImmediatePropagation();
    }

    viewport.addEventListener(
      "wheel",
      (ev) => {
        stopSlideNav(ev);
        ev.preventDefault();
        const factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
        zoomAt(factor, ev.clientX, ev.clientY);
      },
      { passive: false },
    );

    viewport.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      stopSlideNav(ev);
      state.dragging = true;
      state.lx = ev.clientX;
      state.ly = ev.clientY;
      viewport.classList.add("is-dragging");
      viewport.setPointerCapture(ev.pointerId);
    });
    viewport.addEventListener("pointermove", (ev) => {
      if (!state.dragging) return;
      stopSlideNav(ev);
      state.x += ev.clientX - state.lx;
      state.y += ev.clientY - state.ly;
      state.lx = ev.clientX;
      state.ly = ev.clientY;
      apply();
    });
    const endDrag = (ev) => {
      if (!state.dragging) return;
      stopSlideNav(ev);
      state.dragging = false;
      viewport.classList.remove("is-dragging");
    };
    viewport.addEventListener("pointerup", endDrag);
    viewport.addEventListener("pointercancel", endDrag);

    function openLightbox() {
      let lb = document.querySelector(".mp-mermaid-lightbox");
      if (!lb) {
        lb = document.createElement("div");
        lb.className = "mp-mermaid-lightbox";
        lb.innerHTML =
          '<div class="mp-mermaid-shell">' +
          '<div class="mp-mermaid-toolbar">' +
          '<span class="mp-mermaid-hint">Expanded diagram · Esc to close</span>' +
          '<button type="button" data-act="out">−</button>' +
          '<button type="button" data-act="in">+</button>' +
          '<button type="button" data-act="fit">Fit</button>' +
          '<button type="button" data-act="close">Close</button>' +
          "</div>" +
          '<div class="mp-mermaid-viewport" data-lb-viewport></div>' +
          "</div>";
        document.body.appendChild(lb);
        lb.addEventListener("click", (ev) => {
          if (ev.target === lb) closeLightbox();
        });
        document.addEventListener("keydown", (ev) => {
          if (ev.key === "Escape" && lb.classList.contains("open")) closeLightbox();
        });
      }
      const lbViewport = lb.querySelector("[data-lb-viewport]");
      lbViewport.innerHTML = "";
      const clone = mermaidDiv.cloneNode(true);
      const cloneSvg = clone.querySelector("svg");
      lbViewport.appendChild(clone);
      lb.classList.add("open");

      const lbState = { scale: 1, x: 0, y: 0, dragging: false, lx: 0, ly: 0 };
      const { w: cw, h: ch } = svgNaturalSize(cloneSvg);
      cloneSvg.removeAttribute("width");
      cloneSvg.removeAttribute("height");
      cloneSvg.style.maxWidth = "none";
      cloneSvg.style.width = cw + "px";
      cloneSvg.style.height = ch + "px";

      function lbApply() {
        cloneSvg.style.transform =
          "translate(" + lbState.x + "px," + lbState.y + "px) scale(" + lbState.scale + ")";
      }
      function lbFit() {
        const vw = lbViewport.clientWidth;
        const vh = lbViewport.clientHeight;
        const pad = 24;
        lbState.scale = Math.min((vw - pad) / cw, (vh - pad) / ch, 1.5);
        lbState.x = (vw - cw * lbState.scale) / 2;
        lbState.y = (vh - ch * lbState.scale) / 2;
        lbApply();
      }
      function lbZoom(factor, cx, cy) {
        const prev = lbState.scale;
        const next = Math.min(5, Math.max(0.1, prev * factor));
        const rect = lbViewport.getBoundingClientRect();
        const px = (cx ?? rect.left + rect.width / 2) - rect.left;
        const py = (cy ?? rect.top + rect.height / 2) - rect.top;
        lbState.x = px - ((px - lbState.x) * next) / prev;
        lbState.y = py - ((py - lbState.y) * next) / prev;
        lbState.scale = next;
        lbApply();
      }

      lbViewport.onwheel = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        lbZoom(ev.deltaY < 0 ? 1.12 : 1 / 1.12, ev.clientX, ev.clientY);
      };
      lbViewport.onpointerdown = (ev) => {
        if (ev.button !== 0) return;
        lbState.dragging = true;
        lbState.lx = ev.clientX;
        lbState.ly = ev.clientY;
        lbViewport.classList.add("is-dragging");
        lbViewport.setPointerCapture(ev.pointerId);
      };
      lbViewport.onpointermove = (ev) => {
        if (!lbState.dragging) return;
        lbState.x += ev.clientX - lbState.lx;
        lbState.y += ev.clientY - lbState.ly;
        lbState.lx = ev.clientX;
        lbState.ly = ev.clientY;
        lbApply();
      };
      lbViewport.onpointerup = () => {
        lbState.dragging = false;
        lbViewport.classList.remove("is-dragging");
      };

      lb.querySelectorAll("[data-act]").forEach((btn) => {
        btn.onclick = (ev) => {
          ev.stopPropagation();
          const act = btn.getAttribute("data-act");
          if (act === "in") lbZoom(1.2);
          else if (act === "out") lbZoom(1 / 1.2);
          else if (act === "fit") lbFit();
          else if (act === "close") closeLightbox();
        };
      });

      requestAnimationFrame(lbFit);
      window.__mpCloseMermaidLightbox = closeLightbox;
      function closeLightbox() {
        lb.classList.remove("open");
        lbViewport.innerHTML = "";
      }
    }

    toolbar.querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        stopSlideNav(ev);
        const act = btn.getAttribute("data-act");
        if (act === "in") zoomAt(1.2);
        else if (act === "out") zoomAt(1 / 1.2);
        else if (act === "fit") fit();
        else if (act === "expand") openLightbox();
      });
    });

    // Prevent Marp/bespoke from stealing keys while focused in diagram.
    shell.addEventListener("keydown", stopSlideNav);

    requestAnimationFrame(fit);
    window.addEventListener("resize", () => {
      viewport.style.height = availableViewportHeight(shell) + "px";
      fit();
    });
  }

  document.querySelectorAll("div.mermaid").forEach(enhanceDiagram);
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
        shells: document.querySelectorAll(".mp-mermaid-shell").length,
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
      // Let fit() settle after toolbar/viewport layout.
      await new Promise((r) => setTimeout(r, 500));
    }
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
      ? `Embedded Mermaid runtime + interactive controls into ${htmlPath}`
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
