import { test, expect } from "@playwright/test";
import financeFixture from "../../../docs/examples/BA-009-coffee-result.json" with { type: "json" };
import rankingFixture from "../../../docs/examples/BA-008-kazan-coffee.json" with { type: "json" };
import { mockConsents } from "./consent.mock";

// Explicit mock adapter: no LLM, GPU, database, or public tile downloads in CI.
test("browser workflow with explicitly mocked APIs", async ({ page }) => {
  const ranking = rankingFixture.scenarios.covered_BA007_zones.response;
  const profile = structuredClone(
    financeFixture.response.request_snapshot.profile,
  );
  let view = {
    id: profile.conversation_id,
    version: 0,
    profile: {
      ...profile,
      preferences: {
        format: "навынос",
        preferred_districts: [],
        constraints: [],
      },
      confirmation_state: "draft",
    },
    state: "awaiting_confirmation",
    missing_fields: [] as string[],
    extraction_mode: "stub",
    assistant_message: "Mock assistant",
    created_at: "2026-10-23T00:00:00Z",
    updated_at: "2026-10-23T00:00:00Z",
  };
  let history: object[] = [];
  let rent = "";
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.abort(),
  );
  await page.route("**/healthz", (route) =>
    route.fulfill({
      json: { status: "ok", database: "ok", postgis_version: "mock" },
    }),
  );
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.startsWith("/api/v1/data-providers/"))
      return route.fulfill({
        json: path.endsWith("/policy")
          ? { mode: "real", demo_enabled: false, allowed_providers: ["osm"] }
          : [],
      });
    if (path.endsWith("/walking-graph")) return route.fulfill({ json: null });
    if (path.endsWith("/conversations"))
      return route.fulfill({
        json: { ...view, access_token: "explicit-mock-credential-never-real" },
        status: 201,
      });
    if (path.includes("/messages") && route.request().method() === "POST") {
      history = [
        {
          id: "mock-user",
          role: "user",
          content: route.request().postDataJSON().content,
          version: 1,
          created_at: view.created_at,
        },
        {
          id: "mock-assistant",
          role: "assistant",
          content: "Mock: проверьте профиль",
          version: 1,
          created_at: view.created_at,
        },
      ];
      view = { ...view, version: 1 };
      return route.fulfill({ json: view });
    }
    if (path.endsWith("/messages")) return route.fulfill({ json: history });
    if (path.endsWith("/confirm")) {
      view = {
        ...view,
        version: 2,
        state: "confirmed",
        profile: { ...view.profile, confirmation_state: "confirmed" },
      };
      return route.fulfill({ json: view });
    }
    if (path.includes("/conversations/")) return route.fulfill({ json: view });
    if (path.endsWith("/datasets"))
      return route.fulfill({ json: [ranking.candidates.dataset] });
    if (path.endsWith("/rankings")) return route.fulfill({ json: ranking });
    if (path.endsWith("/pois"))
      return route.fulfill({
        json: {
          type: "FeatureCollection",
          features: [],
          returned_count: 0,
          next_offset: null,
          dataset: ranking.candidates.dataset,
        },
      });
    if (path.endsWith("/districts"))
      return route.fulfill({
        json: {
          type: "FeatureCollection",
          features: [],
          dataset: ranking.candidates.dataset,
          truncated: false,
        },
      });
    if (path.endsWith("/calculate")) {
      rent = route.request().postDataJSON().monthly_fixed_costs.rent.value;
      return route.fulfill({ json: financeFixture.response });
    }
    return route.fulfill({ status: 404, json: {} });
  });
  await mockConsents(page);
  await page.goto("/");
  await page
    .getByLabel("Сообщение помощнику")
    .fill("Хочу открыть кофейню в Казани. Бюджет — 2 миллиона рублей");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.getByText("Режим stub · не LLM")).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить профиль →" }).click();
  await page.getByRole("button", { name: "Найти зоны →" }).click();
  await expect(page.locator(".zone-card")).toHaveCount(5);
  await page
    .getByRole("button", { name: "Выбрать зону на карте: 2", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Выбрать зону на карте: 2", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "▥ Сравнение зон" }).click();
  await page.locator(".zone-card").nth(1).click();
  await expect(page.locator(".zone-card").nth(1)).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "К финансовой модели →" }).click();
  await page.getByRole("button", { name: "Загрузить демо-допущения" }).click();
  await page.getByLabel("Аренда", { exact: true }).fill("90000");
  await page.getByRole("button", { name: "Пересчитать модель →" }).click();
  await expect(page.getByLabel("Результат финансового расчёта")).toBeVisible();
  expect(rent).toBe("90000");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.reload();
  await expect(page.getByText("Mock: проверьте профиль")).toBeVisible();
  expect(page.url()).not.toContain("credential");
});

test("Ollama error retains message and permits retry without pretending success", async ({
  page,
}) => {
  await page.route("**/api/v1/geo/datasets", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/healthz", (route) =>
    route.fulfill({ json: { status: "ok", database: "ok" } }),
  );
  await page.route("**/api/v1/conversations", (route) =>
    route.fulfill({
      status: 201,
      json: {
        id: "mock",
        access_token: "mock-only",
        version: 0,
        profile: {
          conversation_id: "mock",
          id: "mock",
          city: null,
          category: null,
          budget: null,
          funding: null,
          preferences: {},
          confirmation_state: "draft",
        },
        state: "collecting",
        missing_fields: ["city"],
        extraction_mode: "rules",
      },
    }),
  );
  await page.route("**/api/v1/conversations/mock/messages", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: { code: "llm_unavailable" } },
    }),
  );
  await mockConsents(page);
  await page.goto("/");
  await page.getByLabel("Сообщение помощнику").fill("Идея бизнеса");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.getByRole("alert")).toContainText("Ollama");
  await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
    "Идея бизнеса",
  );
});
