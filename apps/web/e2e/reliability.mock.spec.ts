import { test, expect, type Page } from "@playwright/test";
import finance from "../../../docs/examples/BA-009-coffee-result.json" with { type: "json" };
import { mockConsents } from "./consent.mock";
import type { Conversation, Profile } from "../src/api";

const pageErrors = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  pageErrors.set(page, errors);
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page)).toEqual([]);
});

// Controlled fault injection, not a live-model evaluation.
async function setup(page: Page, restore = true) {
  const key = { id: "ba016-mock-session", token: "ba016-explicit-mock-token" };
  let view: Conversation = {
    id: key.id,
    version: 2,
    state: "confirmed",
    missing_fields: [] as string[],
    extraction_mode: "stub",
    assistant_message: "Mock: профиль сохранён",
    created_at: "2026-10-25T00:00:00Z",
    updated_at: "2026-10-25T00:00:00Z",
    profile: {
      ...finance.response.request_snapshot.profile,
      conversation_id: key.id,
      preferences: {
        format: "навынос",
        preferred_districts: [],
        constraints: [],
      },
    } as Profile,
  };
  if (restore)
    await page.addInitScript(
      (key) =>
        sessionStorage.setItem("business-ai.guest.v1", JSON.stringify(key)),
      key,
    );
  await page.route("https://tile.openstreetmap.org/**", (r) => r.abort());
  await page.route("**/healthz", (r) =>
    r.fulfill({ json: { status: "ok", database: "ok" } }),
  );
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/datasets")) return route.fulfill({ json: [] });
    if (path.includes("data-providers"))
      return route.fulfill({
        json: path.endsWith("/policy")
          ? { mode: "real", demo_enabled: false, allowed_providers: ["osm"] }
          : [],
      });
    if (path.endsWith("/conversations")) {
      view = {
        ...view,
        version: 0,
        state: "collecting",
        missing_fields: ["city"],
        profile: {
          ...view.profile,
          city: null,
          category: null,
          budget: null,
          confirmation_state: "draft",
        },
      };
      return route.fulfill({
        status: 201,
        json: { ...view, access_token: key.token },
      });
    }
    if (path.endsWith("/messages")) return route.fulfill({ json: [] });
    if (path.endsWith("/profile") && route.request().method() === "PATCH") {
      view = {
        ...view,
        version: view.version + 1,
        state: "awaiting_confirmation",
        profile: {
          ...view.profile,
          ...route.request().postDataJSON().patch,
          confirmation_state: "draft",
        },
      };
    }
    if (path.includes("/conversations/")) return route.fulfill({ json: view });
    return route.fulfill({
      status: 503,
      json: { detail: { code: "bank_catalogue_unavailable" } },
    });
  });
  await mockConsents(page);
  return key;
}

test("REL-01 restores profile and keeps credential out of URL", async ({
  page,
}) => {
  const key = await setup(page);
  await page.goto("/");
  await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  expect(page.url()).not.toContain(key.token);
});

for (const [code, status, message] of [
  ["llm_unavailable", 503, "Ollama"],
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
    await setup(page);
    await page.route("**/messages", (r) =>
      r.request().method() === "POST"
        ? r.fulfill({ status, json: { detail: { code } } })
        : r.fallback(),
    );
    await page.goto("/");
    await page.getByLabel("Сообщение помощнику").fill("Меняю город на Самару");
    await page.getByLabel("Отправить сообщение").press("Enter");
    await expect(page.getByRole("alert")).toContainText(
      new RegExp(message, "i"),
    );
    await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
      "Меняю город на Самару",
    );
    await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  });

test("REL-05 empty geography does not fabricate zones", async ({ page }) => {
  await setup(page);
  await page.goto("/");
  await expect(page.getByText("Нет загруженных геоданных")).toBeVisible();
  await expect(page.locator(".zone-card")).toHaveCount(0);
});

test("REL-06 database health outage is visible", async ({ page }) => {
  await setup(page);
  await page.route("**/healthz", (r) =>
    r.fulfill({ status: 503, json: { detail: "Database is unavailable" } }),
  );
  await page.goto("/");
  await expect(page.getByText("API недоступен", { exact: true })).toBeVisible();
});

test("REL-07 foreign session never reveals profile", async ({ page }) => {
  await setup(page);
  await page.route("**/conversations/ba016-mock-session", (r) =>
    r.fulfill({
      status: 404,
      json: { detail: { code: "conversation_not_found" } },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText("Подтверждён", { exact: true })).toHaveCount(0);
});

test("REL-08 conflict refreshes state without discarding message", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/messages", (r) =>
    r.request().method() === "POST"
      ? r.fulfill({
          status: 409,
          json: { detail: { code: "version_conflict", version: 3 } },
        })
      : r.fallback(),
  );
  await page.goto("/");
  await page.getByLabel("Сообщение помощнику").fill("Бюджет 500000 рублей");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.getByRole("alert")).toContainText("другим запросом");
  await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
    "Бюджет 500000 рублей",
  );
});

test("REL-09 declined assistant consent prevents model request", async ({
  page,
}) => {
  await setup(page, false);
  await page.route(/\/consents$/, async (r) => {
    return r.fulfill({
      json: {
        texts: [],
        consents: [{ purpose: "assistant", status: "declined", revision: 1 }],
      },
    });
  });
  let calls = 0;
  await page.route("**/messages", (r) => {
    if (r.request().method() === "POST") calls++;
    return r.fulfill({ json: [] });
  });
  await page.goto("/");
  await page.getByLabel("Сообщение помощнику").fill("Кофейня");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.getByRole("alert")).toContainText("согласие");
  expect(calls).toBe(0);
});

test("REL-10 long message is bounded before request", async ({ page }) => {
  await setup(page);
  await page.goto("/");
  const input = page.getByLabel("Сообщение помощнику");
  await input.fill("а".repeat(4100));
  await expect(input).toHaveValue("а".repeat(4000));
});

test("REL-11 profile correction clears confirmation", async ({ page }) => {
  await setup(page);
  await page.goto("/");
  await page.getByText("Редактировать профиль ↗").click();
  await page.getByLabel("Город", { exact: true }).fill("Самара");
  await page.getByRole("button", { name: "Сохранить профиль" }).click();
  await expect(page.getByText("Черновик", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Подтвердить профиль →" }),
  ).toBeEnabled();
});

test("REL-12 new conversation leaves previous state behind", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/");
  await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Новая беседа/ }).click();
  await expect(page.getByText("Черновик", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Подтвердить профиль →" }),
  ).toBeDisabled();
});

test("REL-13 bank catalogue failure does not invent offers", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/");
  await page.getByRole("button", { name: "◇ Продукты ВТБ" }).click();
  await expect(page.getByRole("alert")).toContainText("Каталог");
  await expect(page.locator(".product-card")).toHaveCount(0);
});

test("REL-14 finance explicitly labels assumptions and handles API failure", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/");
  await page.getByRole("button", { name: "↗ Финансовая модель" }).click();
  await page.getByRole("button", { name: "Загрузить демо-допущения" }).click();
  await expect(
    page.getByText("синтетические редактируемые допущения", { exact: true }),
  ).toBeVisible();
  await page.route("**/finance/calculate", (r) =>
    r.fulfill({ status: 503, json: { detail: "Unavailable" } }),
  );
  await page.getByRole("button", { name: "Пересчитать модель →" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Результат финансового расчёта")).toHaveCount(0);
});

test("REL-15 mobile navigation remains usable", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "↗ Финансовая модель" }).click();
  await expect(
    page.getByRole("button", { name: "Загрузить демо-допущения" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
