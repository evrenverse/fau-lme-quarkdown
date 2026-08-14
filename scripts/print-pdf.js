#!/usr/bin/env node
/**
 * Print a Quarkdown-rendered HTML directory to PDF via PagedJS + Puppeteer.
 *
 * Mirrors Quarkdown's internal pdf/pdf.js workflow: spawn a local HTTP
 * server pointing at the HTML directory (file:// breaks PagedJS asset
 * loading), launch headless-shell Chromium, wait for `window.isReady()`
 * (PagedJS's page-layout-complete hook), call page.pdf().
 *
 * Usage: node print-pdf.js <html-dir> <output.pdf>
 */

const path = require("path");
const fs = require("fs");
const http = require("http");

const PUPPETEER_CACHE = path.join(
    process.env.HOME, ".cache", "quarkdown-npm", "node_modules", "puppeteer"
);
if (!fs.existsSync(PUPPETEER_CACHE)) {
    console.error(
        "ERROR: Puppeteer not found at " + PUPPETEER_CACHE + ". " +
        "Run 'npm i --prefix ~/.cache/quarkdown-npm puppeteer' once."
    );
    process.exit(1);
}
const puppeteer = require(PUPPETEER_CACHE);

const htmlDir = process.argv[2];
const outFile = process.argv[3];
if (!htmlDir || !outFile) {
    console.error("Usage: print-pdf.js <html-dir> <output.pdf>");
    process.exit(1);
}

const MIME = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css",
    ".js":   "application/javascript",
    ".svg":  "image/svg+xml",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".woff": "font/woff",
    ".woff2":"font/woff2",
    ".ttf":  "font/ttf",
    ".otf":  "font/otf",
    ".json": "application/json",
};

function serve(root) {
    return new Promise((resolve) => {
        const server = http.createServer((req, res) => {
            const url = decodeURIComponent(req.url.split("?")[0]);
            const p = path.join(root, url === "/" ? "/index.html" : url);
            // Reject path traversal.
            if (!p.startsWith(path.resolve(root))) {
                res.writeHead(403); res.end(); return;
            }
            fs.readFile(p, (err, data) => {
                if (err) { res.writeHead(404); res.end(String(err)); return; }
                const mime = MIME[path.extname(p)] || "application/octet-stream";
                res.writeHead(200, { "Content-Type": mime });
                res.end(data);
            });
        });
        server.listen(0, "127.0.0.1", () => {
            resolve({ server, port: server.address().port });
        });
    });
}

(async () => {
    const absRoot = path.resolve(htmlDir);
    const { server, port } = await serve(absRoot);
    const url = `http://127.0.0.1:${port}/index.html`;
    console.error(`Serving ${absRoot} at ${url}`);

    const browser = await puppeteer.launch({
        args: ["--disable-gpu", "--no-sandbox"],
        headless: true,
        protocolTimeout: 0,
    });
    try {
        const page = await browser.newPage();
        page.setDefaultNavigationTimeout(0);
        page.setDefaultTimeout(0);
        await page.goto(url);
        await page.content();
        console.error("Waiting for window.isReady() ...");
        await page.waitForFunction("window.isReady && window.isReady()");

        // PagedJS sometimes leaves "orphan" clones of headings on the
        // chapter's first content page (e.g. when a taller-than-page figure
        // opens the chapter): the heading is duplicated, the orphan keeps the
        // id, and Quarkdown's updateTableOfContentsPageNumbers() resolves via
        // getElementById() which returns the FIRST match — the orphan on the
        // chapter-start page. Symptom: every subsection's ToC entry shows
        // the chapter's start page.
        // Fix: walk the ToC, for any href whose id has >1 matches, re-target
        // the last match (which corresponds to the physically-rendered
        // heading, not the layout-engine orphan) and refresh the page span.
        const tocFix = await page.evaluate(() => {
            const out = { rewritten: 0, kept: 0 };
            document.querySelectorAll('nav[role="table-of-contents"] a[href^="#"]').forEach(a => {
                const href = a.getAttribute("href");
                if (!href || href === "#") { out.kept += 1; return; }
                const id = href.slice(1);
                const all = document.querySelectorAll(`[id="${CSS.escape(id)}"]`);
                if (all.length < 2) { out.kept += 1; return; }
                const last = all[all.length - 1];
                const pagedjsPage = last.closest(".pagedjs_page");
                if (!pagedjsPage) { out.kept += 1; return; }
                const disp = pagedjsPage.dataset.displayPageNumber
                    || pagedjsPage.dataset.pageNumber;
                if (!disp) { out.kept += 1; return; }
                let span = a.querySelector(".toc-page-number");
                if (!span) {
                    span = document.createElement("span");
                    span.className = "toc-page-number";
                    a.appendChild(span);
                }
                span.innerText = disp;
                out.rewritten += 1;
            });
            return out;
        });
        console.error(`ToC orphan-fix: rewritten=${tocFix.rewritten}, kept=${tocFix.kept}`);

        // List of Figures / List of Tables page numbers. PagedJS' page-number
        // pass only fills nav[role="table-of-contents"]; our injected
        // .lme-listing tables are not ToC, so fill their page cells here with
        // the same technique: resolve each page-cell anchor's target id to its
        // rendered .pagedjs_page and write the displayed page number as text.
        // (CSS target-counter(attr(href url)) is unreliable in this build.)
        const lofFix = await page.evaluate(() => {
            let filled = 0;
            document
                .querySelectorAll('table.lme-listing td.page a[href^="#"]')
                .forEach(a => {
                    const id = a.getAttribute("href").slice(1);
                    const all = document.querySelectorAll(`[id="${CSS.escape(id)}"]`);
                    if (!all.length) return;
                    // last match = physically rendered element, not a PagedJS
                    // orphan clone (same rationale as the ToC orphan-fix above).
                    const pagedjsPage = all[all.length - 1].closest(".pagedjs_page");
                    if (!pagedjsPage) return;
                    const disp = pagedjsPage.dataset.displayPageNumber
                        || pagedjsPage.dataset.pageNumber;
                    if (!disp) return;
                    a.textContent = disp;
                    filled += 1;
                });
            return { filled };
        });
        console.error(`LoF/LoT page-fill: filled=${lofFix.filled}`);

        console.error("Page ready. Printing.");
        await page.pdf({
            path: outFile,
            printBackground: true,
            preferCSSPageSize: true,
            // Chrome builds the PDF bookmark tree (sidebar outline) from the
            // tagged heading structure (h1-h6). Both flags are required: the
            // outline is derived from the tagged-PDF accessibility tree.
            tagged: true,
            outline: true,
            timeout: 0,
        });
        console.error("Wrote " + outFile);
    } finally {
        await browser.close();
        await new Promise((r) => server.close(r));
    }
})().catch((err) => {
    console.error(err);
    process.exit(2);
});
