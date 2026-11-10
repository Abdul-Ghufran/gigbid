import type { Page } from "@playwright/test";
import fs from "node:fs";

export const auth = () => JSON.parse(fs.readFileSync("tests/e2e/.auth.json", "utf-8")) as { token: string; email: string; pending: string[] };

/** Sign in by placing the session token where the app keeps it. */
export async function signIn(page: Page, token = auth().token) {
  await page.goto("/login");
  await page.evaluate((t) => localStorage.setItem("gigbid.token", t), token);
}
