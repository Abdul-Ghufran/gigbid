// Print the Playwright HTML report (apps/web/playwright-report) to docs/playwright-report.pdf for the submission.
import { chromium } from "@playwright/test";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const dir = path.resolve(process.cwd(), "playwright-report");
const srv = http.createServer((req, res) => {
  const p = path.join(dir, decodeURIComponent(req.url.split("?")[0]) === "/" ? "index.html" : decodeURIComponent(req.url.split("?")[0]));
  fs.readFile(p, (e, b) => { if (e) { res.writeHead(404); res.end(); } else { res.writeHead(200); res.end(b); } });
}).listen(9333);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 1400 } });
await page.goto("http://127.0.0.1:9333/");
await page.waitForTimeout(2500);
await page.pdf({ path: path.resolve(process.cwd(), "../../docs/playwright-report.pdf"), format: "A4", printBackground: true });
await browser.close();
srv.close();
console.log("docs/playwright-report.pdf written");
