import { test, expect } from "@playwright/test";
import example from "../../../docs/examples/BA-011-coffee.json" with { type: "json" };
import { mockConsents } from "./consent.mock";
import type { Schemas } from "../src/api";

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
  await mockConsents(page);
  let draft: Schemas["LeadDraft"] | null = null;
  let receipt: Schemas["LeadReceipt"] | null = null;
  await page.route(/\/leads$/, (route) =>
    route.fulfill({
      json: {
        drafts: draft ? [draft] : [],
        receipts: receipt ? [receipt] : [],
      },
    }),
  );
  await page.route(
    /\/leads\/drafts(?:\/[^/]+(?:\/confirm|\/submit)?)?$/,
    (route) => {
      const body = route.request().postDataJSON();
      const path = new URL(route.request().url()).pathname;
      expect(route.request().headers()["x-conversation-token"]).toBe(
        credential.token,
      );
      if (path.endsWith("/submit")) {
        expect(body.confirmed).toBe(true);
        expect(body.payload_fingerprint).toBe(draft!.payload_fingerprint);
        receipt = {
          id: "local-demo-receipt",
          draft_id: draft!.id,
          draft_revision: draft!.revision,
          profile_version: 2,
          payload: draft!.payload,
          payload_fingerprint: draft!.payload_fingerprint,
          consents: [],
          created_at: draft!.created_at,
          status: "demo_created",
          sent_to_bank: false,
          message:
            "Демонстрационная заявка создана. Данные в ВТБ не отправлены",
        };
        draft = { ...draft!, state: "submitted" };
        return route.fulfill({ json: receipt });
      }
      if (path.endsWith("/confirm")) {
        draft = { ...draft!, state: "confirmed" };
        return route.fulfill({ json: draft });
      }
      expect(body.fields.budget).toBeNull();
      expect(body.product_ids).toEqual(["vtb-rko"]);
      draft = {
        id: "local-draft",
        revision: 1,
        profile_version: 2,
        profile_snapshot:
          fixture.profile_snapshot as Schemas["BusinessProfile-Output"],
        consents: [],
        payload: {
          fields: body.fields,
          products: fixture.catalogue.products.filter(
            (p) => p.product.id === "vtb-rko",
          ) as Schemas["ProductView"][],
          mode: "demonstration",
          recipient: "local_mock_only",
          catalogue_version: fixture.catalogue.version,
          catalogue_fingerprint: fixture.catalogue.fingerprint,
          field_origins: {},
        },
        payload_fingerprint: "a".repeat(64),
        state: "draft",
        stale: false,
        created_at: "2026-10-23T00:00:00Z",
        updated_at: "2026-10-23T00:00:00Z",
      };
      return route.fulfill({ json: draft, status: 201 });
    },
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
  const lead = page.getByRole("region", { name: "Демонстрационная заявка" });
  await lead.getByRole("checkbox", { name: /Расчётно-кассовое/ }).check();
  await lead.getByLabel("Бюджет заявки").fill("");
  await expect(
    lead.getByRole("button", { name: "Подготовить демо-черновик →" }),
  ).toBeDisabled();
  await lead
    .getByRole("button", {
      name: "Отказаться: Маркетинговые рекомендации",
      exact: true,
    })
    .click();
  await lead
    .getByRole("button", {
      name: "Согласиться: Подготовка и демонстрационная передача",
      exact: true,
    })
    .click();
  await lead
    .getByRole("button", { name: "Подготовить демо-черновик →" })
    .click();
  await lead.getByLabel("Я проверил все поля и выбранные продукты").check();
  await lead
    .getByRole("button", { name: "Подтвердить состав заявки", exact: true })
    .click();
  await lead
    .getByLabel(
      "Подтверждаю создание демонстрационной заявки без отправки в банк",
    )
    .check();
  await lead
    .getByRole("button", { name: "Создать демонстрационную заявку →" })
    .click();
  await expect(
    lead.getByRole("heading", {
      name: "Демонстрационная заявка создана. Данные в ВТБ не отправлены",
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.reload();
  await page.getByRole("button", { name: "◇ Продукты ВТБ" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Демонстрационная заявка создана. Данные в ВТБ не отправлены",
      exact: true,
    }),
  ).toBeVisible();
});
