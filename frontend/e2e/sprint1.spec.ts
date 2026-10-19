import { expect, test } from "@playwright/test";

/**
 * Sprint 1 UI test cases TC_20-TC_23 from the user stories document.
 * Backend cases TC_01-TC_19 live in backend/tests/test_sprint1_acceptance.py.
 */
const API_BASE = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

type ApiAgent = { id: string; status: string; capabilities: string[] };

test.describe("Sprint 1 workspace", () => {
  test("TC_20 submit a brief from the UI shows spawned agents with status and reason", async ({
    page,
  }) => {
    await page.goto("/office");
    await expect(page.getByTestId("command-form")).toBeVisible({ timeout: 30_000 });

    await page
      .getByTestId("request-input")
      .fill("Audit this repository for security vulnerabilities and write a findings report.");
    const submitted = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" && /\/api\/v1\/tasks(\?|$)/.test(response.url()),
    );
    await page.getByTestId("assign-work").click();
    expect((await submitted).ok()).toBe(true);
    await page.getByTestId("tab-work").click();

    await expect(page.getByTestId("workflow-status")).toBeVisible({ timeout: 30_000 });
    const reasons = page.locator('[data-testid^="node-reason-"]');
    await expect(reasons.first()).toContainText("Selected for:");
    expect(await reasons.count()).toBeGreaterThanOrEqual(2);
    await expect(page.locator('[data-testid^="node-status-"]').first()).toHaveAttribute(
      "data-status",
      /.+/,
    );
    await expect(page.getByTestId("skipped-agents")).toContainText("data-cleaner-agent");
  });

  test("TC_21 empty brief is blocked in the UI", async ({ page }) => {
    await page.goto("/office");
    await expect(page.getByTestId("command-form")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("request-input").fill("");

    await expect(page.getByTestId("assign-work")).toBeDisabled();
    await expect(page.getByTestId("brief-hint")).toContainText("Enter a brief");
  });

  test("TC_22 agents page matches the list-agents API", async ({ page, request }) => {
    const response = await request.get(`${API_BASE}/api/v1/agents?include_disabled=true`);
    expect(response.ok()).toBe(true);
    const agents = (await response.json()) as ApiAgent[];
    expect(agents.length).toBeGreaterThan(0);

    await page.goto("/office");
    await page.getByTestId("tab-agents").click();
    const registry = page.getByTestId("agent-registry");
    await expect(registry).toBeVisible();
    await expect(registry.locator('[data-testid^="registry-row-"]')).toHaveCount(agents.length);

    for (const agent of agents) {
      await expect(page.getByTestId(`registry-status-${agent.id}`)).toHaveAttribute(
        "data-status",
        agent.status,
      );
      const chips = page.getByTestId(`registry-capabilities-${agent.id}`).locator("[data-capability]");
      await expect(chips).toHaveCount(agent.capabilities.length);
      for (const capability of agent.capabilities) {
        await expect(
          page
            .getByTestId(`registry-capabilities-${agent.id}`)
            .locator(`[data-capability="${capability}"]`),
        ).toBeVisible();
      }
    }
  });

  test("TC_23 backend errors are shown clearly and the page stays usable", async ({ page }) => {
    await page.goto("/office");
    await expect(page.getByTestId("command-form")).toBeVisible({ timeout: 30_000 });

    // A vague brief is answered with a clarifying question instead of spawning agents.
    await page.getByTestId("request-input").fill("help me");
    await page.getByTestId("assign-work").click();
    await expect(page.getByRole("alert").filter({ hasText: "What should the agents do?" })).toBeVisible();
    await expect(page.getByTestId("request-input")).toBeEditable();
    await page.getByTestId("request-input").fill("Summarise the latest research on vector databases.");
    await expect(page.getByTestId("assign-work")).toBeEnabled();

    // A rejected enrollment names the field that is wrong.
    await page.getByTestId("tab-agents").click();
    await expect(page.getByTestId("enroll-form")).toBeVisible();
    await page.getByTestId("enroll-name").fill(`E2E Agent ${Date.now()}`);
    await page.getByTestId("enroll-description").fill("Created by the Sprint 1 browser test.");
    await page.getByTestId("enroll-submit").click();
    await expect(page.getByTestId("enroll-error")).toContainText("capabilities");

    // A duplicate name is rejected with a clear message.
    await page.getByTestId("enroll-name").fill("Security Agent");
    await page.getByTestId("enroll-capability-review.quality").check();
    await page.getByTestId("enroll-submit").click();
    await expect(page.getByTestId("enroll-error")).toContainText("already enrolled");
    await expect(page.getByTestId("enroll-submit")).toBeEnabled();
  });
});
