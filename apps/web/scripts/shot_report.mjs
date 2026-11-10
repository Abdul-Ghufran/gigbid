import { chromium } from "@playwright/test";
import path from "node:path";
import { pathToFileURL } from "node:url";
const root = path.resolve(process.cwd(), "../..");
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 794, height: 1123 } });
await p.goto(pathToFileURL(path.join(root, "docs/report/report.html")).href);
await p.screenshot({ path: process.argv[2], fullPage: false, clip: { x: 0, y: Number(process.argv[3] || 0), width: 794, height: 1123 } });
await b.close();
