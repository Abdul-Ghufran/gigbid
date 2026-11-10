import { expect, test } from "@playwright/test";
import { auth, signIn } from "./helpers";

test("onboarding: create account, choose a persona, land in a populated inbox", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.getByLabel("Email").fill(`onb-${Date.now()}@gigbid.test`);
  await page.getByLabel("Password").fill("onboarding-pass-1");
  await page.getByTestId("auth-submit").click();
  await expect(page).toHaveURL(/onboarding/);
  await page.getByTestId("persona-data").click();
  await expect(page.getByTestId("rate")).toHaveValue("30");
  await page.getByTestId("connects-budget").fill("50");
  await page.getByTestId("finish-onboarding").click();
  await expect(page).toHaveURL(/inbox/, { timeout: 120_000 });
  await expect(page.getByTestId("job-card").first()).toBeVisible({ timeout: 60_000 });
});

test("approve a proposal: evidence on hover, dry-run preview, submitted exactly once", async ({ page }) => {
  const jobId = auth().pending[0];
  await signIn(page);
  await page.goto(`/studio/${jobId}`);
  await expect(page.getByTestId("approval-panel")).toBeVisible();
  const claim = page.getByTestId("claim").first();
  await claim.focus();
  await expect(page.getByTestId("evidence-pop").first()).toBeVisible();
  await expect(page.getByTestId("connects-cost")).toContainText(/\d+/);
  await page.getByText("Dry-run preview").click();
  await expect(page.getByTestId("dry-run")).toContainText(jobId);
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("run-timeline")).toContainText("Submitting", { timeout: 120_000 });
  await expect(page.getByText(/Run done/)).toBeVisible({ timeout: 120_000 });
  await page.goto(`/jobs/${jobId}`);
  await expect(page.getByTestId("job-status")).toHaveText("submitted", { timeout: 30_000 });
});

test("reject a proposal with a reason", async ({ page }) => {
  const jobId = auth().pending[1];
  await signIn(page);
  await page.goto(`/studio/${jobId}`);
  await page.getByTestId("reject").click();
  await expect(page.getByTestId("confirm-reject")).toBeDisabled();
  await page.getByTestId("reject-reason").fill("Client timezone does not work for me");
  await page.getByTestId("confirm-reject").click();
  await expect(page.getByText(/Run done/)).toBeVisible({ timeout: 120_000 });
  await page.goto("/inbox");
  await page.getByRole("tab", { name: "All" }).click();
  await expect(page.locator(`[data-status="rejected"]`).first()).toBeVisible({ timeout: 30_000 });
});

test("edit a draft: edit is re-checked by compliance and comes back for approval", async ({ page }) => {
  const jobId = auth().pending[2];
  await signIn(page);
  await page.goto(`/studio/${jobId}`);
  await page.getByTestId("edit-mode").click();
  const editor = page.getByTestId("editor");
  const original = await editor.inputValue();
  // add a contact detail the Compliance Guard must strip, plus a real edit
  await editor.fill(original + "\n\nYou can also reach me at someone@example.com. Looking forward to working together on this.");
  await page.getByTestId("approve").click(); // label switches to "Save edits & re-check"
  await expect(page.getByText(/Run (done|interrupted)/)).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "Reload studio" }).click();
  await expect(page.getByTestId("approval-panel")).toBeVisible();
  await expect(page.getByText(/contact details/).first()).toBeVisible();
  await page.getByTestId("edit-mode").click();
  await expect(page.getByTestId("editor")).not.toContainText("someone@example.com");
  await expect(page.getByTestId("editor")).toHaveValue(/Looking forward to working together/);
});

test("degraded mode: marketplace down shows a banner and keeps the app usable", async ({ page, request }) => {
  const reg = await (await request.post("http://127.0.0.1:8011/api/auth/register",
    { data: { email: `deg-${Date.now()}@gigbid.test`, password: "degraded-pass-1", display_name: "" } })).json();
  await page.goto("http://127.0.0.1:8011/login");
  await page.evaluate((t) => localStorage.setItem("gigbid.token", t), reg.token);
  await request.post("http://127.0.0.1:8011/api/auth/onboarding", { headers: { Authorization: `Bearer ${reg.token}` },
    data: { persona_key: "ai", marketplace: "gigsim", hourly_rate: 45, min_project: 400, weekly_connects_budget: 60, saved_searches: [] } });
  await page.goto("http://127.0.0.1:8011/inbox");
  await expect(page.getByTestId("degraded-banner")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("degraded-banner")).toContainText("Marketplace unavailable");
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
});
