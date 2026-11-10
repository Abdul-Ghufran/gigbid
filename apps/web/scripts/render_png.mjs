// Render docs/images/*.mmd to PNG with a locally installed Mermaid in headless Chromium (no network upload).
// Usage (from apps/web): node scripts/render_png.mjs
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "../..");
const img = path.join(root, "docs", "images");
const mermaidJs = fs.readFileSync(path.join(process.cwd(), "node_modules", "mermaid", "dist", "mermaid.min.js"), "utf-8");
const browser = await chromium.launch();
for (const f of fs.readdirSync(img).filter((x) => x.endsWith(".mmd"))) {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 2 });
  const src = fs.readFileSync(path.join(img, f), "utf-8");
  await page.setContent(`<html><body style="margin:0;background:#fff"><pre class="mermaid">${src.replace(/</g, "&lt;")}</pre></body></html>`);
  await page.addScriptTag({ content: mermaidJs });
  await page.evaluate(async () => { mermaid.initialize({ startOnLoad: false, theme: "default" }); await mermaid.run(); });
  const el = await page.$("pre.mermaid svg");
  await el.screenshot({ path: path.join(img, f.replace(".mmd", ".png")) });
  console.log("rendered", f);
}
await browser.close();
