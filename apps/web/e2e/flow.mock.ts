import { expect, type Page } from "@playwright/test";
import finance from "../../../docs/examples/BA-009-coffee-result.json" with { type: "json" };
import geo from "../../../docs/examples/BA-008-kazan-coffee.json" with { type: "json" };
import bank from "../../../docs/examples/BA-011-coffee.json" with { type: "json" };
import type { Conversation, Schemas } from "../src/api";
import { mockConsents } from "./consent.mock";
export const ranking = geo.scenarios.covered_BA007_zones.response;
export const key = {
  id: "design02-explicit-mock-session",
  token: "design02-test-credential-only",
};
export async function mockGeography(page: Page) {
  await page.route("https://tile.openstreetmap.org/**", (r) => r.abort());
  await page.route("**/api/v1/geo/**", (r) => {
    const path = new URL(r.request().url()).pathname;
    if (path.endsWith("/datasets"))
      return r.fulfill({ json: [ranking.candidates.dataset] });
    if (path.endsWith("/rankings")) return r.fulfill({ json: ranking });
    if (path.endsWith("/walking-graph")) return r.fulfill({ json: null });
    return r.fulfill({
      json: {
        type: "FeatureCollection",
        features: [],
        returned_count: 0,
        next_offset: null,
        truncated: false,
        dataset: ranking.candidates.dataset,
      },
    });
  });
  await page.route("**/api/v1/data-providers/**", (r) =>
    r.fulfill({
      json: new URL(r.request().url()).pathname.endsWith("/policy")
        ? { mode: "real", demo_enabled: false, allowed_providers: ["osm"] }
        : [],
    }),
  );
}
export async function setupFlow(page: Page, restore = true) {
  await page.route("**/api/v2/industry-capabilities", (r) =>
    r.fulfill({ json: { enabled: false, industries: [] } }),
  );
  let view: Conversation = {
    id: key.id,
    version: 2,
    profile: {
      ...finance.response.request_snapshot.profile,
      conversation_id: key.id,
      preferences: {
        format: "навынос",
        preferred_districts: [],
        constraints: [],
      },
    },
    state: "confirmed",
    missing_fields: [],
    extraction_mode: "stub",
    assistant_message: "Mock: профиль сохранён",
    created_at: "2026-10-28T00:00:00Z",
    updated_at: "2026-10-28T00:00:00Z",
  } as Conversation;
  let history: object[] = [
    {
      id: "saved",
      role: "assistant",
      content: "Mock: история восстановлена",
      version: 2,
      created_at: view.created_at,
    },
  ];
  if (restore)
    await page.addInitScript(
      (key) =>
        sessionStorage.setItem("business-ai.guest.v1", JSON.stringify(key)),
      key,
    );
  await page.route("**/api/v1/**", async (r) => {
    const path = new URL(r.request().url()).pathname;
    if (path.endsWith("/conversations")) {
      view = {
        ...view,
        version: 0,
        state: "collecting",
        missing_fields: ["category", "city", "budget"],
        profile: {
          ...view.profile,
          city: null,
          category: null,
          budget: null,
          confirmation_state: "draft",
        },
      };
      history = [];
      return r.fulfill({
        status: 201,
        json: { ...view, access_token: key.token },
      });
    }
    if (path.endsWith("/messages")) {
      if (r.request().method() === "POST") {
        const content = r.request().postDataJSON().content;
        view = {
          ...view,
          version: view.version + 1,
          state: "awaiting_confirmation",
          missing_fields: [],
          profile: {
            ...view.profile,
            ...finance.response.request_snapshot.profile,
            conversation_id: key.id,
            confirmation_state: "draft",
          },
        };
        history = [
          ...history,
          {
            id: `u${view.version}`,
            role: "user",
            content,
            version: view.version,
            created_at: view.created_at,
          },
          {
            id: `a${view.version}`,
            role: "assistant",
            content: "Mock: проверьте ваш проект",
            version: view.version,
            created_at: view.created_at,
          },
        ];
        return r.fulfill({ json: view });
      }
      return r.fulfill({ json: history });
    }
    if (path.endsWith("/profile/confirm")) {
      view = {
        ...view,
        version: view.version + 1,
        state: "confirmed",
        profile: { ...view.profile, confirmation_state: "confirmed" },
      };
      return r.fulfill({ json: view });
    }
    if (path.endsWith("/profile") && r.request().method() === "PATCH") {
      view = {
        ...view,
        version: view.version + 1,
        state: "awaiting_confirmation",
        profile: {
          ...view.profile,
          ...r.request().postDataJSON().patch,
          confirmation_state: "draft",
        },
      };
      return r.fulfill({ json: view });
    }
    if (path.endsWith("/calculate")) {
      const input = r.request().postDataJSON();
      const result = structuredClone(finance.response);
      result.request_snapshot = input;
      if (input.monthly_fixed_costs.rent.value === "90000")
        result.scenarios.find(
          (s) => s.name === "base",
        )!.metrics.operating_result.value = "275000.00";
      return r.fulfill({ json: result });
    }
    if (path.endsWith("/bank-products"))
      return r.fulfill({ json: bank.response.catalogue });
    if (path.endsWith("/bank-products/matches"))
      return r.fulfill({
        json: {
          ...bank.response,
          needs_snapshot: r.request().postDataJSON().needs,
          profile_version: view.version,
          profile_snapshot: view.profile,
        },
      });
    if (path.includes("/reports")) {
      if (path.endsWith("/file"))
        return r.fulfill({
          body:
            new URL(r.request().url()).searchParams.get("format") === "pdf"
              ? "%PDF-explicit-mock"
              : JSON.stringify({ synthetic: true }),
          contentType:
            new URL(r.request().url()).searchParams.get("format") === "pdf"
              ? "application/pdf"
              : "application/json",
        });
      return r.fulfill({
        json: {
          id: "test-report",
          profile_version: view.version,
          created_at: view.created_at,
          snapshot_sha256: "a".repeat(64),
          pdf_sha256: "b".repeat(64),
          status: "current",
          reasons: [],
          missing_sections: [],
          json_bytes: 100,
          pdf_bytes: 100,
        },
      });
    }
    if (path.includes("/conversations/")) return r.fulfill({ json: view });
    return r.fulfill({
      status: 404,
      json: { detail: { code: "explicit_mock_unhandled" } },
    });
  });
  await mockGeography(page);
  await mockConsents(page);
  return { key, getView: () => view };
}
export async function openChat(page: Page) {
  await expect(
    page.getByRole("heading", { name: /Где лучше открыть/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "← Назад", exact: true }).click();
  await page
    .getByRole("button", { name: "Вернуться в диалог", exact: true })
    .click();
}
export async function goFinance(page: Page) {
  await expect(
    page.getByRole("heading", { name: /Где лучше открыть/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Найти локации", exact: true })
    .click();
  await expect(page.locator(".zone-card")).toHaveCount(5);
  await page
    .getByRole("button", { name: "Продолжить к расчётам", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Рассчитать сценарии", exact: true })
    .click();
  await expect(page.getByLabel("Результат финансового расчёта")).toBeVisible();
}
export async function goBank(page: Page) {
  await goFinance(page);
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: /Что поможет/ }),
  ).toBeVisible();
}
export async function expertNeeds(page: Page) {
  await page
    .getByText("Изменить или дополнить потребности", { exact: true })
    .click();
}
export function profile(view: Conversation): Schemas["BusinessProfile-Output"] {
  return view.profile;
}
