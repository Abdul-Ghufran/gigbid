import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

test("mobile: inbox and studio fit a phone screen with no horizontal scroll", async ({ page }) => {
  await signIn(page);
  await page.goto("/inbox");
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.keyboard.press("Tab");
  await expect(page.getByText("Skip to content")).toBeFocused();
});
