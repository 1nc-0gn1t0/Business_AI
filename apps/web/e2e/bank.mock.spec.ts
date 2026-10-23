import { test, expect } from "@playwright/test";
import example from "../../../docs/examples/BA-011-coffee.json" with { type: "json" };

test("demo catalogue, explicit needs, protected matching and mobile layout (mock API)", async ({
  page,
}) => {
  const fixture = example.response;
  const credential = {
    id: fixture.profile_snapshot.conversation_id,
    token: "explicit-mock-token-only",
  };
  await page.addInitScript(
    (key) =>
      sessionStorage.setItem("business-ai.guest.v1", JSON.stringify(key)),
    credential,
  );
  await page.route("**/healthz", (route) =>
    route.fulfill({ json: { status: "ok", database: "ok" } }),
  );
  await page.route("**/api/v1/geo/datasets", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/conversations/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/messages")) return route.fulfill({ json: [] });
    if (path.endsWith("/bank-products/matches")) {
      const input = route.request().postDataJSON();
      expect(input.expected_version).toBe(2);
      expect(input.needs.registration_status).toBe("ip");
      expect(route.request().headers()["x-conversation-token"]).toBe(
        credential.token,
      );
      return route.fulfill({ json: fixture });
    }
    return route.fulfill({
      json: {
        id: credential.id,
        version: 2,
        state: "confirmed",
        profile: fixture.profile_snapshot,
        missing_fields: [],
        extraction_mode: "stub",
        created_at: "2026-10-23T00:00:00Z",
        updated_at: "2026-10-23T00:00:00Z",
      },
    });
  });
  await page.route("**/api/v1/bank-products", (route) =>
    route.fulfill({ json: fixture.catalogue }),
  );
  await page.goto("/");
  await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "◇ Продукты ВТБ" }).click();
  await expect(page.getByText("Демо-каталог", { exact: true })).toBeVisible();
  await page
    .getByLabel("Регистрация бизнеса", { exact: true })
    .selectOption("ip");
  await page
    .getByLabel("Канал продаж", { exact: true })
    .selectOption("offline");
  await page
    .getByLabel("Планируете принимать оплату картами", { exact: true })
    .selectOption("true");
  await page
    .getByLabel("Нужен расчётный счёт", { exact: true })
    .selectOption("true");
  await page
    .getByRole("button", { name: "Подобрать по потребностям →" })
    .click();
  await expect(
    page.getByText("Подбор выполнен по явным правилам"),
  ).toBeVisible();
  await expect(page.locator(".bank-product-card")).toHaveCount(6);
  await expect(
    page.getByText(/Потенциальные соответствия по проверенным источникам: 0/),
  ).toBeVisible();
  expect(page.url()).not.toContain(credential.token);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByLabel("Канал продаж", { exact: true }).selectOption("online");
  await expect(page.getByText("Подбор выполнен по явным правилам")).toHaveCount(
    0,
  );
});
