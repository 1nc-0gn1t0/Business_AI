import { test, expect } from "@playwright/test";
import { mockConsents } from "./consent.mock";

for (const width of [1440, 768, 390]) {
  test(`DESIGN-01 ${width}px: accessible navigation and draft survive stage changes (mock APIs)`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.setViewportSize({ width, height: 1050 });
    await page.route("**/healthz", (r) =>
      r.fulfill({ json: { status: "ok", database: "ok" } }),
    );
    await page.route("**/api/v1/geo/datasets", (r) => r.fulfill({ json: [] }));
    await page.route("**/api/v1/data-providers/**", (r) =>
      r.fulfill({ json: [] }),
    );
    await mockConsents(page);
    await page.goto("/");
    await page.getByRole("button", { name: "Кофейня", exact: true }).click();
    const idea = await page.getByLabel("Сообщение помощнику").inputValue();
    await page
      .getByRole("button", { name: "AI-помощник", exact: true })
      .click();
    await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(idea);
    await page.getByLabel("Сообщение помощнику").fill("Несохранённый текст");
    await page.getByRole("button", { name: "⌖ Карта и локации" }).click();
    await expect(
      page.getByText("Нет загруженных геоданных", { exact: true }),
    ).toBeVisible();
    expect(await page.locator(".zone-card").count()).toBe(0);
    await page.getByRole("button", { name: "Отчёт", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Подготовить отчёт" }),
    ).toBeDisabled();
    await page
      .getByRole("button", { name: "AI-помощник", exact: true })
      .click();
    await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
      "Несохранённый текст",
    );
    await expect(
      page.getByRole("button", { name: "AI-помощник", exact: true }),
    ).toHaveAttribute("aria-current", "step");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("button", { name: "Обзор проекта", exact: true })
      .click();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  });
}
