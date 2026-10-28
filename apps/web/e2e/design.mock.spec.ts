import { test, expect } from "@playwright/test";
import { setupFlow, goFinance, openChat } from "./flow.mock";
for (const width of [1440, 768, 390])
  test(`DESIGN-02 ${width}px: minimal start, keyboard, dialog and guarded back flow`, async ({
    page,
  }) => {
    await setupFlow(page, false);
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/#business-ai");
    await expect(
      page.getByRole("heading", { name: "Какой бизнес вы хотите открыть?" }),
    ).toBeVisible();
    await expect(page.getByRole("navigation")).toHaveCount(0);
    await expect(page.locator(".app-sidebar")).toHaveCount(0);
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "Перейти к содержимому" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await page
      .getByLabel("Сообщение помощнику")
      .fill("Кофейня в Казани, бюджет 2 миллиона");
    await page.getByLabel("Отправить сообщение").click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(
      page
        .getByRole("dialog")
        .getByRole("button", { name: "Продолжить", exact: true }),
    ).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
      "Кофейня в Казани, бюджет 2 миллиона",
    );
    await page.getByLabel("Отправить сообщение").click();
    await page.getByLabel("Согласен на использование ассистента").check();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Продолжить", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Всё верно?" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Вернуться в диалог" }).click();
    await page.getByLabel("Сообщение помощнику").fill("Несохранённый текст");
    await page
      .getByRole("button", { name: "Проверить параметры проекта" })
      .click();
    await page.getByRole("button", { name: "Вернуться в диалог" }).click();
    await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
      "Несохранённый текст",
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("button", { name: "Проверить параметры проекта" })
      .click();
    await page.getByRole("button", { name: "Продолжить", exact: true }).click();
    await goFinance(page);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "← Назад", exact: true }).click();
    await page.locator(".zone-card").nth(1).click();
    await page.getByRole("button", { name: "Продолжить к расчётам" }).click();
    await expect(
      page.getByRole("button", { name: "Рассчитать сценарии" }),
    ).toBeVisible();
    await expect(page.getByLabel("Результат финансового расчёта")).toHaveCount(
      0,
    );
  });

test("DESIGN-02 progressive bank questions send explicit needs and do not infer unknowns", async ({
  page,
}) => {
  await setupFlow(page);
  let body: Record<string, unknown> = {};
  await page.route("**/bank-products/matches", (r) => {
    body = r.request().postDataJSON();
    return r.fallback();
  });
  await page.goto("/#business-ai");
  await goFinance(page);
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await page.getByRole("button", { name: "Да", exact: true }).click();
  await page.getByRole("button", { name: "ИП", exact: true }).click();
  await page.getByRole("button", { name: "Да", exact: true }).click();
  await page
    .getByRole("button", { name: "Физическая точка", exact: true })
    .click();
  await page.getByRole("button", { name: "Пока не знаю", exact: true }).click();
  await page
    .getByRole("button", { name: "Подобрать по потребностям →", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Возможности для вашего проекта" }),
  ).toBeVisible();
  expect(body.needs).toEqual({
    needs_settlement_account: true,
    registration_status: "ip",
    accepts_card_payments: true,
    sales_channel: "offline",
    financing_interest: null,
  });
  expect(body).not.toHaveProperty("profile");
});

test("DESIGN-02 withdrawn consent at the server prevents inference and requires new explicit choice", async ({
  page,
}) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await openChat(page);
  let modelCalls = 0;
  await page.route("**/messages", (r) => {
    if (r.request().method() === "POST") modelCalls++;
    return r.fallback();
  });
  await page.route(/\/consents$/, (r) =>
    r.fulfill({
      json: {
        consents: [
          {
            purpose: "assistant",
            status: "withdrawn",
            revision: 2,
            text_version: "assistant-demo-v1",
          },
        ],
      },
    }),
  );
  await page.getByLabel("Сообщение помощнику").fill("Новый бюджет");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(
    page
      .getByRole("dialog")
      .getByRole("button", { name: "Продолжить", exact: true }),
  ).toBeDisabled();
  expect(modelCalls).toBe(0);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Назад", exact: true })
    .click();
  await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
    "Новый бюджет",
  );
});
