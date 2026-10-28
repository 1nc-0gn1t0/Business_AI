import { test, expect, type Page } from "@playwright/test";
import { setupFlow, openChat, goFinance, goBank, key } from "./flow.mock";
const pageErrors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  pageErrors.set(page, errors);
  page.on("pageerror", (e) => errors.push(e.message));
});
test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page)).toEqual([]);
});

test("REL-01 restores profile and keeps credential out of URL", async ({
  page,
}) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await expect(
    page.getByRole("heading", { name: /Где лучше открыть/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "← Назад", exact: true }).click();
  await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: /Где лучше открыть/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Продолжить к расчётам" }),
  ).toBeDisabled();
  expect(page.url()).not.toContain(key.token);
});
for (const [code, status, message] of [
  ["llm_unavailable", 503, "Ollama"],
  ["llm_model_missing", 503, "Qwen"],
  ["llm_server_error", 502, "технической"],
  ["database_capacity_busy", 503, "соединения"],
  ["llm_timeout", 504, "время"],
  ["llm_invalid_response", 502, "ответ"],
  ["request_body_too_large", 413, "слишком велик"],
  ["request_text_too_long", 422, "длинный"],
  ["resource_quota_exceeded", 429, "лимит сохраняемых"],
  ["request_capacity_busy", 429, "занят"],
  ["llm_queue_full", 429, "Очередь"],
  ["llm_queue_timeout", 429, "ожидания"],
] as const)
  test(`REL-chat-${code} preserves draft and confirmed state`, async ({
    page,
  }) => {
    if (code === "resource_quota_exceeded")
      await page.setViewportSize({ width: 390, height: 844 });
    await setupFlow(page);
    await page.route("**/messages", (r) =>
      r.request().method() === "POST"
        ? r.fulfill({
            status,
            json: { detail: { code } },
            headers: { "X-Request-ID": "d".repeat(32) },
          })
        : r.fallback(),
    );
    await page.goto("/#business-ai");
    await openChat(page);
    await page.getByLabel("Сообщение помощнику").fill("Меняю город на Самару");
    await page.getByLabel("Отправить сообщение").press("Enter");
    await expect(page.getByRole("alert")).toContainText(
      new RegExp(message, "i"),
    );
    await expect(page.getByRole("alert")).toContainText("d".repeat(32));
    await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
      "Меняю город на Самару",
    );
    await page
      .getByRole("button", { name: "Проверить параметры проекта" })
      .click();
    await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  });

test("REL-05 empty geography does not fabricate zones", async ({ page }) => {
  await setupFlow(page);
  await page.route("**/geo/datasets", (r) => r.fulfill({ json: [] }));
  await page.goto("/#business-ai");
  await expect(
    page.getByText("Нет загруженных геоданных", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".zone-card")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Продолжить к расчётам" }),
  ).toBeDisabled();
});
test("REL-06 database outage is visible without an infrastructure dashboard", async ({
  page,
}) => {
  await setupFlow(page);
  await page.route(`**/conversations/${key.id}`, (r) =>
    r.fulfill({
      status: 503,
      json: { detail: { code: "database_unavailable" } },
    }),
  );
  await page.goto("/#business-ai");
  await expect(page.getByRole("alert")).toContainText("База данных");
  await expect(
    page.getByRole("heading", { name: /Где лучше открыть/ }),
  ).toHaveCount(0);
});
test("REL-07 foreign session never reveals profile", async ({ page }) => {
  await setupFlow(page);
  await page.route(`**/conversations/${key.id}`, (r) =>
    r.fulfill({
      status: 404,
      json: { detail: { code: "conversation_not_found" } },
    }),
  );
  await page.goto("/#business-ai");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Не удалось открыть проект" }),
  ).toBeVisible();
  await expect(page.getByText("Подтверждён", { exact: true })).toHaveCount(0);
});
test("REL-08 conflict refreshes state without discarding message", async ({
  page,
}) => {
  const { getView } = await setupFlow(page);
  await page.route("**/messages", (r) =>
    r.request().method() === "POST"
      ? r.fulfill({
          status: 409,
          json: { detail: { code: "version_conflict", version: 3 } },
        })
      : r.fallback(),
  );
  await page.goto("/#business-ai");
  await openChat(page);
  await page.route(`**/conversations/${key.id}`, (r) =>
    r.fulfill({ json: { ...getView(), version: 3 } }),
  );
  await page.getByLabel("Сообщение помощнику").fill("Бюджет 500000 рублей");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.getByRole("alert")).toContainText("другим запросом");
  await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
    "Бюджет 500000 рублей",
  );
  await expect(
    page.getByText("Mock: история восстановлена", { exact: true }),
  ).toBeVisible();
});
test("REL-09 declined assistant consent prevents model request", async ({
  page,
}) => {
  await setupFlow(page, false);
  let calls = 0;
  await page.route("**/messages", (r) => {
    if (r.request().method() === "POST") calls++;
    return r.fulfill({ json: [] });
  });
  await page.goto("/#business-ai");
  await page.getByLabel("Сообщение помощнику").fill("Кофейня");
  await page.getByLabel("Отправить сообщение").click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Назад", exact: true })
    .click();
  expect(calls).toBe(0);
  await expect(page.getByLabel("Сообщение помощнику")).toHaveValue("Кофейня");
});
test("REL-10 long message is bounded before request", async ({ page }) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await openChat(page);
  await page.getByLabel("Сообщение помощнику").fill("а".repeat(4100));
  await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
    "а".repeat(4000),
  );
});
test("REL-11 profile correction clears confirmation", async ({ page }) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await page.getByRole("button", { name: "← Назад", exact: true }).click();
  await page.getByRole("button", { name: "Изменить", exact: true }).click();
  await page.getByLabel("Город", { exact: true }).fill("Самара");
  await page.getByRole("button", { name: "Сохранить профиль" }).click();
  await expect(page.getByText("Черновик", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Продолжить", exact: true }),
  ).toBeEnabled();
  await expect(page.locator(".zone-card")).toHaveCount(0);
});
test("REL-12 new conversation leaves previous state behind", async ({
  page,
}) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await expect(
    page.getByRole("heading", { name: /Где лучше открыть/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Новый проект", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Какой бизнес вы хотите открыть?" }),
  ).toBeVisible();
  await expect(page.getByLabel("Сообщение помощнику")).toBeEmpty();
  await expect(
    page.getByText("Mock: история восстановлена", { exact: true }),
  ).toHaveCount(0);
});
test("REL-13 bank catalogue failure does not invent offers", async ({
  page,
}) => {
  await setupFlow(page);
  await page.route("**/api/v1/bank-products", (r) =>
    r.fulfill({
      status: 503,
      json: { detail: { code: "bank_catalogue_unavailable" } },
    }),
  );
  await page.goto("/#business-ai");
  await goBank(page);
  await expect(page.getByRole("alert")).toContainText("Каталог");
  await expect(page.locator(".bank-product-card")).toHaveCount(0);
});
test("REL-14 finance explicitly labels assumptions and handles API failure", async ({
  page,
}) => {
  await setupFlow(page);
  await page.route("**/finance/calculate", (r) =>
    r.fulfill({ status: 503, json: { detail: "Unavailable" } }),
  );
  await page.goto("/#business-ai");
  await page
    .getByRole("button", { name: "Найти локации", exact: true })
    .click();
  await page.getByRole("button", { name: "Продолжить к расчётам" }).click();
  await expect(
    page.getByText(/Синтетические редактируемые допущения/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Рассчитать сценарии" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Результат финансового расчёта")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Продолжить", exact: true }),
  ).toBeDisabled();
});
test("REL-15 mobile back navigation remains usable", async ({ page }) => {
  await setupFlow(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#business-ai");
  await goFinance(page);
  await page.getByRole("button", { name: "← Назад", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Где лучше открыть/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
