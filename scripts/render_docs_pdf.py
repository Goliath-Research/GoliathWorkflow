#!/usr/bin/env python3
"""Print the MkDocs HTML site to a single PDF via Playwright.

Material for MkDocs renders Mermaid into *closed* shadow roots. Chromium's
print-to-PDF path often omits closed-shadow content, so diagrams look like
missing icons/shapes. This script serves ``site/`` over HTTP, re-renders
Mermaid into the light DOM, waits for MathJax, then prints.
"""
from __future__ import annotations

import io
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT_DIR = ROOT / "site-pdf"
OUT_PDF = OUT_DIR / "MethylPipeline-Documentation.pdf"

PREFERRED = [
    "index.html",
    "overview/methylpipeline-platform-overview/index.html",
    "theory/index.html",
    "usage/index.html",
    "usage/alignment-engines/index.html",
    "usage/03-sample-prep-and-qc/index.html",
    "usage/18-samd-study-lifecycle/index.html",
    "architecture/layer-model/index.html",
    "architecture/end-to-end-workflow/index.html",
    "deployment/operator-journey/index.html",
    "regulatory/index.html",
    "regulatory/change-management-plan/index.html",
    "reference/documentation-toolchain/index.html",
    "CONTRIBUTING/index.html",
]

# Injected before print: re-render Mermaid into light DOM + materialize mask icons.
PREPARE_FOR_PDF_JS = r"""
async () => {
  const decodeEntities = (s) => s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");

  const parseMaskUrl = (mask) => {
    if (!mask || mask === 'none') return null;
    const start = mask.indexOf('url(');
    if (start < 0) return null;
    let rest = mask.slice(start + 4).trim();
    const q = (rest[0] === '"' || rest[0] === "'") ? rest[0] : null;
    if (q) {
      rest = rest.slice(1);
      const end = rest.lastIndexOf(q);
      if (end < 0) return null;
      rest = rest.slice(0, end);
    } else {
      const end = rest.indexOf(')');
      rest = end < 0 ? rest : rest.slice(0, end);
    }
    return rest.replace(/\\"/g, '"').replace(/\\'/g, "'");
  };

  const decodeSvgDataUrl = (url) => {
    const comma = url.indexOf(',');
    if (comma < 0) return null;
    const meta = url.slice(0, comma);
    const payload = url.slice(comma + 1);
    if (meta.includes('base64')) return atob(payload);
    try { return decodeURIComponent(payload); } catch { return payload; }
  };

  // 1) Mermaid: Material uses closed shadow roots; flatten to light DOM for PDF.
  let mermaidCount = 0;
  const hosts = [...document.querySelectorAll('.mermaid, pre.mermaid')];
  if (hosts.length) {
    const html = await (await fetch(location.href)).text();
    const re = /<pre class="mermaid"><code>([\s\S]*?)<\/code><\/pre>/g;
    const blocks = [];
    let m;
    while ((m = re.exec(html))) blocks.push(decodeEntities(m[1]));

    // Ensure mermaid global exists (Material loads it lazily).
    if (typeof mermaid === 'undefined') {
      await new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = 'https://unpkg.com/mermaid@11/dist/mermaid.min.js';
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
    // Compact layout for print: natural SVG size (not 100% page width), then fit.
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      themeVariables: {
        fontSize: '12px',
        fontFamily: 'Helvetica, Arial, sans-serif',
      },
      flowchart: {
        useMaxWidth: false,
        htmlLabels: true,
        nodeSpacing: 18,
        rankSpacing: 28,
        padding: 8,
        curve: 'basis',
      },
      sequence: {
        useMaxWidth: false,
        actorMargin: 24,
        messageMargin: 24,
        mirrorActors: false,
      },
    });

    // A4 content ≈ 182×265mm. Cap diagrams so a figure stays on one page and
    // does not expand to full page width (Mermaid useMaxWidth default).
    const MAX_W_PX = 480;
    const MAX_H_PX = 320;
    const MIN_SCALE = 0.55;

    const fitSvg = (svg) => {
      if (!svg) return;
      let vw = 0, vh = 0;
      const vb = svg.getAttribute('viewBox');
      if (vb) {
        const p = vb.trim().split(/[\s,]+/).map(Number);
        if (p.length === 4 && p[2] > 0 && p[3] > 0) {
          vw = p[2];
          vh = p[3];
        }
      }
      if (!vw || !vh) {
        try {
          const bb = svg.getBBox();
          vw = bb.width || 1;
          vh = bb.height || 1;
          svg.setAttribute('viewBox', `${bb.x} ${bb.y} ${vw} ${vh}`);
        } catch (_) {
          vw = parseFloat(svg.getAttribute('width')) || MAX_W_PX;
          vh = parseFloat(svg.getAttribute('height')) || MAX_H_PX;
        }
      }
      let scale = Math.min(MAX_W_PX / vw, MAX_H_PX / vh, 1);
      // Ultra-wide strips: avoid micro-text; rely on max-width instead.
      if (vw / vh > 3.2 && scale < MIN_SCALE) scale = MIN_SCALE;
      const w = Math.max(1, Math.round(vw * scale));
      const h = Math.max(1, Math.round(vh * scale));
      svg.setAttribute('width', String(w));
      svg.setAttribute('height', String(h));
      svg.style.cssText = [
        `width:${w}px`,
        `height:${h}px`,
        'max-width:100%',
        'max-height:85mm',
        'display:block',
        'margin:0.4rem auto',
      ].join(';');
    };

    for (let i = 0; i < hosts.length; i++) {
      const host = hosts[i];
      const src = blocks[i] || host.textContent || '';
      if (!src.trim()) continue;
      const id = `pdf_mermaid_${i}`;
      try {
        const { svg } = await mermaid.render(id, src);
        const wrap = document.createElement('div');
        wrap.className = 'mermaid pdf-mermaid-light';
        wrap.innerHTML = svg;
        const el = wrap.querySelector('svg');
        fitSvg(el);
        host.replaceWith(wrap);
        mermaidCount++;
      } catch (err) {
        const pre = document.createElement('pre');
        pre.className = 'mermaid-error';
        pre.textContent = 'Mermaid render failed: ' + (err?.message || String(err));
        host.replaceWith(pre);
      }
    }
  }

  // 2) Material mask-image icons → real inline SVG (belt-and-suspenders for print).
  let iconCount = 0;
  const materialize = (el, pseudo) => {
    const cs = getComputedStyle(el, pseudo);
    const url = parseMaskUrl(cs.webkitMaskImage || cs.maskImage);
    if (!url || !url.startsWith('data:image/svg')) return;
    const svgText = decodeSvgDataUrl(url);
    if (!svgText || !svgText.includes('<svg')) return;
    const color = (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)')
      ? cs.backgroundColor
      : getComputedStyle(el).color;
    if (el.querySelector(':scope > .pdf-materialized-icon')) return;
    const wrap = document.createElement('span');
    wrap.className = 'pdf-materialized-icon';
    wrap.setAttribute('aria-hidden', 'true');
    wrap.innerHTML = svgText;
    const svg = wrap.querySelector('svg');
    if (!svg) return;
    svg.setAttribute('fill', 'currentColor');
    svg.style.width = '1.15em';
    svg.style.height = '1.15em';
    svg.style.display = 'block';
    wrap.style.color = color;
    wrap.style.display = 'inline-flex';
    wrap.style.alignItems = 'center';
    wrap.style.marginRight = '0.45em';
    wrap.style.verticalAlign = 'middle';
    el.classList.add('pdf-icon-host');
    el.insertBefore(wrap, el.firstChild);
    iconCount++;
  };
  for (const el of document.querySelectorAll('.md-typeset .admonition-title')) {
    materialize(el, '::before');
  }
  for (const el of document.querySelectorAll('.md-typeset summary')) {
    materialize(el, '::after');
  }
  for (const el of document.querySelectorAll('.task-list-control .task-list-indicator')) {
    materialize(el, '::before');
  }

  // 3) MathJax
  if (window.MathJax?.typesetPromise) {
    try { await MathJax.typesetPromise(); } catch (_) { /* ignore */ }
  }

  return { mermaidCount, iconCount, lightSvg: document.querySelectorAll('.pdf-mermaid-light svg').length };
}
"""

PRINT_CSS = """
.pdf-icon-host::before,
.pdf-icon-host::after {
  display: none !important;
  content: none !important;
  -webkit-mask-image: none !important;
  mask-image: none !important;
  background: none !important;
}
.pdf-mermaid-light {
  overflow: visible !important;
  text-align: center !important;
  page-break-inside: avoid !important;
  break-inside: avoid !important;
  margin: 0.6rem auto !important;
  max-width: 100% !important;
}
.pdf-mermaid-light svg {
  max-width: 100% !important;
  max-height: 85mm !important;
  height: auto !important;
  display: block !important;
  margin: 0 auto !important;
}
@media print {
  * {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  .pdf-mermaid-light {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }
}
"""


class _SiteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def log_message(self, format, *args):  # noqa: A003
        return


def _start_server() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _SiteHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address[:2]
    return httpd, f"http://{host}:{port}"


def _collect_pages() -> list[Path]:
    pages: list[Path] = []
    for rel in PREFERRED:
        path = SITE / rel
        if path.is_file():
            pages.append(path)
    cap = 40
    for path in sorted(SITE.rglob("index.html")):
        if path in pages or "404" in path.parts:
            continue
        pages.append(path)
        if len(pages) >= cap:
            break
    if not pages:
        raise SystemExit("No HTML pages found under site/")
    return pages


def _page_url(base: str, path: Path) -> str:
    rel = path.relative_to(SITE).as_posix()
    if rel.endswith("index.html"):
        rel = rel[: -len("index.html")]
    return f"{base}/{rel}"


def main() -> None:
    if not SITE.is_dir():
        raise SystemExit(f"Missing site/ at {SITE}; run mkdocs build first")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages = _collect_pages()
    httpd, base = _start_server()
    # Brief settle for bind
    time.sleep(0.1)

    pdf_bytes: list[bytes] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            for i, path in enumerate(pages):
                page = context.new_page()
                url = _page_url(base, path)
                page.goto(url, wait_until="networkidle", timeout=120_000)
                # Allow Material's lazy Mermaid CDN fetch to finish when present.
                page.wait_for_timeout(600)
                page.add_style_tag(content=PRINT_CSS)
                stats = page.evaluate(PREPARE_FOR_PDF_JS)
                page.wait_for_timeout(200)
                pdf_bytes.append(
                    page.pdf(
                        format="A4",
                        print_background=True,
                        margin={
                            "top": "16mm",
                            "bottom": "16mm",
                            "left": "14mm",
                            "right": "14mm",
                        },
                    )
                )
                page.close()
                rel = path.relative_to(SITE)
                print(
                    f"rendered {i + 1}/{len(pages)} {rel} "
                    f"(mermaid={stats.get('mermaidCount')} "
                    f"icons={stats.get('iconCount')} "
                    f"svg={stats.get('lightSvg')})"
                )
            browser.close()
    finally:
        httpd.shutdown()

    try:
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        for blob in pdf_bytes:
            reader = PdfReader(io.BytesIO(blob))
            for pg in reader.pages:
                writer.add_page(pg)
        with OUT_PDF.open("wb") as fh:
            writer.write(fh)
        print(f"wrote {OUT_PDF} ({len(writer.pages)} pages)")
    except Exception as exc:  # noqa: BLE001
        print(f"pypdf merge unavailable ({exc}); writing per-page PDFs")
        for i, blob in enumerate(pdf_bytes):
            (OUT_DIR / f"page-{i:03d}.pdf").write_bytes(blob)
        OUT_PDF.write_bytes(pdf_bytes[0])
        print(f"wrote {OUT_PDF} (first page only) + page-*.pdf")


if __name__ == "__main__":
    main()
