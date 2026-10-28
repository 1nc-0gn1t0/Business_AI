import { test, expect } from "@playwright/test";
import { setupFlow, key, openChat } from "./flow.mock";

test("browser workflow with explicitly mocked APIs and server-checked transitions", async ({
  page,
}) => {
  await setupFlow(page, false);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#business-ai");
  await page
    .getByLabel("Сообщение помощнику")
    .fill("Хочу открыть кофейню в Казани. Бюджет — 2 миллиона рублей");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("Согласен на использование ассистента").check();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Продолжить", exact: true })
    .click();
  await expect(page.getByRole("heading", { name: "Всё верно?" })).toBeVisible();
  await page.getByRole("button", { name: "Вернуться в диалог" }).click();
  await expect(page.getByText("Ответ без AI-модели")).toBeVisible();
  await page
    .getByRole("button", { name: "Проверить параметры проекта" })
    .click();
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await page
    .getByRole("button", { name: "Найти локации", exact: true })
    .click();
  await expect(page.locator(".zone-card")).toHaveCount(5);
  await page
    .getByRole("button", { name: "Выбрать зону на карте: 2", exact: true })
    .click();
  await expect(page.locator(".zone-card").nth(1)).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.locator(".zone-card").nth(2).click();
  await expect(
    page.getByRole("button", { name: "Выбрать зону на карте: 3", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("button", { name: "Продолжить к расчётам", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Рассчитать сценарии", exact: true })
    .click();
  await expect(page.getByLabel("Результат финансового расчёта")).toBeVisible();
  await page.getByLabel("Аренда", { exact: true }).fill("90000");
  await expect(
    page.getByRole("button", { name: "Продолжить", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Пересчитать модель →" }).click();
  await expect(page.locator(".scenario-card.base > strong")).toContainText(
    "275",
  );
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await page.getByRole("button", { name: "Продолжить без подбора" }).click();
  await expect(
    page.getByRole("heading", { name: "Ваш бизнес-план готов" }),
  ).toBeVisible();
  for (const format of ["PDF", "JSON"]) {
    const download = page.waitForEvent("download");
    await page
      .getByRole("button", { name: `Скачать ${format}`, exact: true })
      .click();
    expect((await download).suggestedFilename()).toMatch(
      /BusinessAI-report-test-report\.(pdf|json)/,
    );
  }
  await page.getByRole("button", { name: "← Назад", exact: true }).click();
  await page.getByRole("button", { name: "← Назад", exact: true }).click();
  await expect(page.getByLabel("Аренда", { exact: true })).toHaveValue("90000");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: /Где лучше открыть/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Продолжить к расчётам" }),
  ).toBeDisabled();
  await openChat(page);
  await expect(
    page.getByText("Mock: проверьте ваш проект", { exact: true }),
  ).toBeVisible();
  expect(page.url()).not.toContain(key.token);
  expect(errors).toEqual([]);
});

test("Ollama error retains message and permits retry without pretending success", async ({
  page,
}) => {
  await setupFlow(page);
  await page.route("**/messages", (r) =>
    r.request().method() === "POST"
      ? r.fulfill({
          status: 503,
          json: { detail: { code: "llm_unavailable" } },
        })
      : r.fallback(),
  );
  await page.goto("/#business-ai");
  await openChat(page);
  await page.getByLabel("Сообщение помощнику").fill("Идея бизнеса");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.getByRole("alert")).toContainText("Помощник временно недоступен");
  await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
    "Идея бизнеса",
  );
});
