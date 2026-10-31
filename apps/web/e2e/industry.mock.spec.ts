import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { setupFlow } from "./flow.mock";
import { industryCatalog, industryFixture } from "./industry.fixture";

for (const industry of [
  "online_school",
  "auto_repair",
  "generic",
  "coffee_shop",
])
  test(`U-04 ${industry}: adaptive confirmation, reload and honest result`, async ({
    page,
  }) => {
    await setupFlow(page, false);
    let view = industryFixture(industry);
    view.conversation.version = 0;
    view.profile.revision = 0;
    let writes = 0;
    await page.route("**/api/v2/industry-capabilities", (r) =>
      r.fulfill({ json: { enabled: true, industries: industryCatalog } }),
    );
    await page.route("**/api/v2/conversations/**", async (r) => {
      const path = new URL(r.request().url()).pathname;
      if (path.endsWith("/analysis-result")) {
        await r.fulfill({
          json: {
            schema_version: "analysis-result-v2",
            conversation_id: view.conversation.id,
            profile_revision: view.profile.revision,
            assessed_at: "2026-10-31T00:00:00Z",
            state: "partial",
            profile: view.profile,
            plan: view.plan,
            financial: null,
            sections: [
              {
                id: "finance",
                state: "missing",
                explanation: "Недостаточно подтверждённых финансовых вводных.",
              },
            ],
            limitations: ["Explicit mock fixture; not live evidence"],
          },
        });
        return;
      }
      if (r.request().method() !== "GET") {
        writes++;
        view = industryFixture(industry, writes > 1, path.endsWith("/confirm"));
      }
      expect(r.request().headers()["x-conversation-token"]).toBeTruthy();
      await r.fulfill({ json: view });
    });
    await page.route("**/api/v1/conversations/*/messages?*", (r) =>
      r.fulfill({
        json: [
          {
            id: "u04-fixture",
            role: "assistant",
            content: view.conversation.assistant_message,
            version: view.conversation.version,
            created_at: view.conversation.created_at,
          },
        ],
      }),
    );
    await page.route(
      "**/api/v1/conversations/design02-explicit-mock-session",
      (r) => r.fulfill({ json: view.conversation }),
    );
    if (industry === "online_school")
      await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/#business-ai");
    await page.getByLabel("Сообщение помощнику").fill(view.profile.idea);
    await page.getByLabel("Отправить сообщение").click();
    await page.getByLabel("Согласен на использование ассистента").check();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Продолжить", exact: true })
      .click();
    await expect(page.getByRole("log")).toContainText(view.plan.next_question!);
    await page
      .getByLabel("Сообщение помощнику")
      .fill("Уточнённые пользователем параметры: explicit browser fixture");
    await page.getByLabel("Отправить сообщение").click();
    await expect(
      page.getByRole("heading", { name: "Ваш проект", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Продолжить", exact: true }).click();
    if (industry === "coffee_shop") {
      await expect(
        page.getByRole("heading", { name: /Где лучше открыть/ }),
      ).toBeVisible();
      return;
    }
    await expect(
      page.getByRole("heading", { name: "Предварительный результат" }),
    ).toBeVisible();
    await expect(
      page.getByText(/Недостаточно подтверждённых финансовых вводных/),
    ).toBeVisible();
    await expect(page.locator(".maplibregl-map")).toHaveCount(0);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await mkdir("../../docs/qa/u-06/mock", { recursive: true });
    await page.screenshot({
      path: `../../docs/qa/u-06/mock/${industry}.png`,
      fullPage: true,
    });
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Предварительный результат" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Изменить проект" }).click();
    await expect(
      page.getByRole("heading", { name: "Ваш проект", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Вернуться в диалог" }).click();
    await expect(page.getByRole("log")).toBeVisible();
  });
