import { expect, test } from "@playwright/test";

test.describe("Agent Mesh smoke (J-2)", () => {
  test("office loads with brand and API badge", async ({ page }) => {
    await page.goto("/office");
    await expect(page.getByTestId("brand")).toHaveText("Agent Mesh");
    await expect(page.getByTestId("office-tabs")).toBeVisible();
    await expect(page.getByTestId("command-form")).toBeVisible({ timeout: 30_000 });
  });

  test("submit brief reaches a terminal workflow status via Demo Mode", async ({ page }) => {
    await page.goto("/office");
    await expect(page.getByTestId("command-form")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("tab-command").click();
    await expect(page.getByTestId("command-form")).toBeVisible();

    await page.getByRole("button", { name: "Advanced" }).click();
    await page.getByTestId("pick-agents").check();
    await page.getByTestId("agent-general-agent").check();

    await page.getByTestId("request-input").fill("Say hello from the office smoke test.");
    await page.getByTestId("assign-work").click();

    const status = page.getByTestId("workflow-status");
    await expect(status).toBeVisible({ timeout: 30_000 });
    await expect(status).toHaveAttribute("data-status", /completed|failed|cancelled/, {
      timeout: 90_000,
    });
    await expect(status).toHaveAttribute("data-status", "completed");
  });
});
