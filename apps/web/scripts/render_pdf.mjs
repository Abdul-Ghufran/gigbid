// Render docs/report/report.html to docs/report/GigBid_RnD_Report.pdf with headless Chromium (A4).
// Usage (from apps/web): node scripts/render_pdf.mjs
import { chromium } from "@playwright/test";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(process.cwd(), "../..");
const html = path.join(root, "docs", "report", "report.html");
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(pathToFileURL(html).href, { waitUntil: "networkidle" });
await page.pdf({ path: path.join(root, "docs", "report", "GigBid_RnD_Report.pdf"), format: "A4", printBackground: true,
  displayHeaderFooter: true, headerTemplate: "<span></span>",
  footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#64748b">GigBid · AI-4016 R&D report · page <span class="pageNumber"></span> / <span class="totalPages"></span></div>',
  margin: { top: "14mm", bottom: "16mm", left: "13mm", right: "13mm" } });
await browser.close();
console.log("PDF written");
