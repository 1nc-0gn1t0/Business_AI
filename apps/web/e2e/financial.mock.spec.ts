// UI contract fixtures only. PostGIS/math/live Qwen are verified separately.
import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import financial from "./fixtures/financial-scenarios.json" with { type: "json" };
import type { Schemas } from "../src/api";
import { setupFlow } from "./flow.mock";
import { industryCatalog, industryFixture } from "./industry.fixture";

for (const width of [1440, 768, 390]) {
  test(`U-05 ${width}: no-map finance, what-if, review and reload`, async ({
    page,
  }) => {
    await setupFlow(page, false);
    await page.setViewportSize({ width, height: 950 });
    const profile = industryFixture("auto_repair", true, true);
    profile.plan.stages = ["finance", "partial_result"];
    profile.plan.capabilities = profile.plan.capabilities.map((c) =>
      c.id === "finance.analysis"
        ? { ...c, status: "available", method: "financial_v2.auto_repair" }
        : c,
    );
    const view = structuredClone(
      financial,
    ) as unknown as Schemas["FinancialView"];
    view.document.profile_revision = profile.profile.revision;
    let draftSaved = false;
    let previewCalls = 0;
    await page.route("**/api/v2/industry-capabilities", (r) =>
      r.fulfill({
        json: {
          enabled: true,
          finance_v2_enabled: true,
          industries: industryCatalog,
        },
      }),
    );
    await page.route("**/api/v2/conversations/**", async (r) => {
      const path = new URL(r.request().url()).pathname;
      expect(r.request().headers()["x-conversation-token"]).toBeTruthy();
      if (!path.includes("financial-scenarios"))
        return r.fulfill({ json: profile });
      if (path.endsWith("what-if")) {
        previewCalls++;
        expect(r.request().postDataJSON().updates[0].base).toBe("110000");
        const result = structuredClone(view.result!.result);
        result.scenarios[1].operating_result = "490000.00";
        return r.fulfill({
          json: {
            persisted: false,
            input_revision: view.document.revision,
            result,
          },
        });
      }
      if (r.request().method() === "PATCH") {
        draftSaved = true;
        view.document.revision++;
        view.document.entries!.rent.base = "110000";
        view.document.entries!.rent.low = "110000";
        view.document.entries!.rent.high = "110000";
        view.document.entries!.rent.review = "proposed";
        view.needs_review = ["rent"];
        view.missing = ["rent"];
        view.result = null;
      }
      if (path.endsWith("review")) {
        expect(r.request().postDataJSON().confirm).toEqual(["rent"]);
        view.document.revision++;
        view.document.entries!.rent.review = "confirmed";
        view.needs_review = [];
        view.missing = [];
      }
      if (path.endsWith("calculate")) {
        view.result = structuredClone(
          financial.result,
        ) as unknown as Schemas["FinancialSnapshot"];
        view.result.result.scenarios[1].operating_result = "490000.00";
      }
      return r.fulfill({ json: view });
    });
    await page.route(
      "**/api/v1/conversations/design02-explicit-mock-session",
      (r) => r.fulfill({ json: profile.conversation }),
    );
    await page.addInitScript(() =>
      sessionStorage.setItem(
        "business-ai.guest.v1",
        JSON.stringify({
          id: "design02-explicit-mock-session",
          token: crypto.randomUUID() + crypto.randomUUID(),
        }),
      ),
    );
    const bad: string[] = [];
    page.on("pageerror", (e) => bad.push(e.message));
    await page.goto("/#business-ai");
    await expect(
      page.getByRole("heading", {
        name: "Сколько может приносить ваш бизнес?",
      }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Базовый" })).toBeVisible();
    await page
      .getByText("Ввести или проверить параметры", { exact: true })
      .click();
    const rent = page.getByRole("textbox", { name: "Аренда", exact: true });
    await rent.fill("110000");
    await expect(
      page.getByRole("heading", { name: "При заданных параметрах" }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Проверить без сохранения" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Пробный расчёт · не сохранён" }),
    ).toBeVisible();
    expect(previewCalls).toBe(1);
    expect(draftSaved).toBe(false);
    await page
      .getByRole("button", { name: "Сохранить вводные для проверки" })
      .click();
    await page.getByRole("checkbox", { name: "Проверено: Аренда" }).check();
    await page
      .getByRole("button", { name: "Использовать выбранные значения" })
      .click();
    await page.getByRole("button", { name: "Рассчитать три сценария" }).click();
    await expect(page.getByRole("heading", { name: "Базовый" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "Базовый" })).toBeVisible();
    expect(
      await page
        .locator("body")
        .evaluate((el) => el.scrollWidth <= window.innerWidth),
    ).toBe(true);
    expect(bad).toEqual([]);
    await page
      .getByRole("heading", { name: "Сколько может приносить ваш бизнес?" })
      .scrollIntoViewIfNeeded();
    await mkdir("../../docs/qa/u-05/screenshots", { recursive: true });
    await page.screenshot({
      path: `../../docs/qa/u-05/screenshots/financial-mock-${width}.png`,
      fullPage: true,
    });
  });
}
