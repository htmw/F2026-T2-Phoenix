import { expect, test } from "@playwright/test";

/**
 * Sprint 2 UI coverage for Build tab, DAG surface, and login page.
 */
test.describe("Sprint 2 office surfaces", () => {
  test("Build tab shows the workflow builder palette", async ({ page }) => {
    await page.goto("/office");
    await expect(page.getByTestId("office-tabs")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("tab-build").click();
    await expect(page.getByTestId("workflow-builder")).toBeVisible();
    await expect(page.getByTestId("builder-request")).toBeVisible();
    await expect(page.getByTestId("builder-palette")).toBeVisible();
    await expect(page.getByTestId("builder-empty")).toBeVisible();
    await expect(page.getByTestId("builder-preview")).toBeDisabled();
    await expect(page.getByTestId("builder-run")).toBeDisabled();
  });

  test("Work tab exposes a DAG surface after a demo run starts", async ({ page }) => {
    await page.goto("/office");
    await expect(page.getByTestId("command-form")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("tab-command").click();
    await page.getByRole("button", { name: "Advanced" }).click();
    await page.getByTestId("pick-agents").check();
    await page.getByTestId("agent-general-agent").check();
    await page.getByTestId("request-input").fill("Sprint 2 DAG smoke: say hello once.");

    const submitted = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" && /\/api\/v1\/tasks(\?|$)/.test(response.url()),
    );
    await page.getByTestId("assign-work").click();
    expect((await submitted).ok()).toBe(true);

    await page.getByTestId("tab-work").click();
    await expect(page.getByTestId("workflow-dag")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("workflow-status")).toHaveAttribute(
      "data-status",
      /completed|failed|cancelled|running|queued/,
      { timeout: 90_000 },
    );
  });

  test("login page loads with operator continue path", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByTestId("login-page")).toBeVisible();
    await expect(page.getByTestId("login-operator")).toBeVisible();
    await expect(page.getByTestId("login-continue")).toBeVisible();
  });
});
