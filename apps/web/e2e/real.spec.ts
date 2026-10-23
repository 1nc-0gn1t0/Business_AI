import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { env } from "node:process";
import type { Ranking, Schemas } from "../src/api";

// Opt-in test against existing Compose and installed Qwen. No route mocks or traces.
test("real Qwen → confirmed profile → PostGIS zones → finance recalculation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto("/");
  await expect(page.getByText("API и PostGIS доступны")).toBeVisible();
  await page.locator(".assistant-consent>summary").click();
  await page
    .getByLabel("Согласен на использование ассистента", { exact: true })
    .check();
  const prompt = "Хочу открыть кофейню в Казани. Бюджет — 2 миллиона рублей";
  await page.getByLabel("Сообщение помощнику").fill(prompt);
  const turnResponse = page.waitForResponse(
    (r) => r.url().endsWith("/messages") && r.request().method() === "POST",
    { timeout: 210_000 },
  );
  await page.getByLabel("Отправить сообщение").click();
  const turn = await turnResponse;
  expect(turn.ok()).toBe(true);
  const extracted = (await turn.json()) as Schemas["ConversationView"];
  expect(extracted.extraction_mode).toBe("ollama");
  expect(extracted.profile.city).toBe("Казань");
  expect(extracted.profile.category).toContain("кофейн");
  expect(Number(extracted.profile.budget)).toBe(2_000_000);
  await expect(page.getByText("Локальная Qwen · Ollama")).toBeVisible();
  await page.getByText("Редактировать профиль ↗").click();
  await page.getByLabel("Формат", { exact: true }).fill("навынос");
  await page.getByLabel("Источник средств").selectOption("own_funds");
  await page.getByRole("button", { name: "Сохранить профиль" }).click();
  await expect(
    page.getByRole("button", { name: "Подтвердить профиль →" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Подтвердить профиль →" }).click();
  await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(prompt, { exact: true })).toBeVisible();
  await expect(page.getByText("Подтверждён", { exact: true })).toBeVisible();
  const rankResponse = page.waitForResponse((r) =>
    r.url().endsWith("/rankings"),
  );
  await page.getByRole("button", { name: "Найти зоны →" }).click();
  const rank = await rankResponse;
  expect(rank.ok()).toBe(true);
  const ranking = (await rank.json()) as Ranking;
  expect(ranking.candidates.features.length).toBeGreaterThan(1);
  expect(
    ranking.evaluations.filter((e) => e.score !== null).length,
  ).toBeGreaterThan(1);
  await expect(page.locator(".zone-card")).toHaveCount(
    ranking.candidates.features.length,
  );
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Zoom out" }).click();
  await expect(page.locator(".zone-marker")).toHaveCount(
    ranking.candidates.features.length,
  );
  await page
    .getByRole("button", { name: "Выбрать зону на карте: 2", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Выбрать зону на карте: 2", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  // Wait for real vector overlays and raster tiles to paint without replacing their data.
  await expect(page.locator(".map-problem")).toHaveCount(0);
  await page.waitForTimeout(1500);
  const directory = env.BA010_ARTIFACT_DIR || "../../docs/screenshots";
  await mkdir(directory, { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${directory}/BA-010-map.png`,
    fullPage: true,
  });
  // BA-013 real PostGIS network; no recorded geometry or route interception.
  const walking = page.getByRole("region", { name: "Пешеходная доступность" });
  await walking
    .getByText("Задать точку координатами WGS84", { exact: true })
    .click();
  await walking.getByLabel("Долгота точки").fill("49.119");
  await walking.getByLabel("Широта точки").fill("55.788");
  await walking
    .getByRole("button", { name: "Использовать координаты" })
    .click();
  const walkHttp = page.waitForResponse((r) => r.url().endsWith("/catchment"));
  await walking
    .getByRole("button", { name: "Рассчитать пешую доступность →" })
    .click();
  const walked = await walkHttp;
  expect(walked.ok()).toBe(true);
  const walkResult = (await walked.json()) as Schemas["CatchmentResult"];
  expect(walkResult.status).toBe("ok");
  expect(walkResult.network!.features.length).toBeGreaterThan(10);
  expect(walkResult.reachable_poi_count).toBeLessThan(
    walkResult.straight_line_poi_count,
  );
  await expect(
    walking.getByLabel("Результат пешеходного анализа"),
  ).toBeVisible();
  await page.getByLabel("Карта зон Казани").scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500);
  await page
    .locator(".map-wrap")
    .screenshot({ path: "../../docs/screenshots/BA-013-walking-map.png" });
  await walking.screenshot({
    path: "../../docs/screenshots/BA-013-walking-panel.png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await walking.screenshot({
    path: "../../docs/screenshots/BA-013-walking-mobile.png",
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await writeFile(
    "../../docs/screenshots/BA-013-verification.json",
    JSON.stringify(
      {
        checked_at: new Date().toISOString(),
        services:
          "real Qwen + PostGIS + walking graph + existing complete workflow",
        graph_version: walkResult.graph!.graph_version,
        poi_data_version: walkResult.poi_data_version,
        counts: {
          network: walkResult.reachable_poi_count,
          straight: walkResult.straight_line_poi_count,
        },
        runtime_ms: walkResult.runtime_ms,
      },
      null,
      2,
    ),
  );
  await page.getByRole("button", { name: "▥ Сравнение зон" }).click();
  await page.locator(".zone-card").nth(1).click();
  await expect(page.locator(".zone-card").nth(1)).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${directory}/BA-010-compare.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "К финансовой модели →" }).click();
  await page.getByRole("button", { name: "Загрузить демо-допущения" }).click();
  const financeResponse = page.waitForResponse((r) =>
    r.url().endsWith("/finance/calculate"),
  );
  await page.getByRole("button", { name: "Пересчитать модель →" }).click();
  const baselineResponse = await financeResponse;
  expect(baselineResponse.ok()).toBe(true);
  const baseline = (await baselineResponse.json()) as Schemas["FinanceResult"];
  await expect(page.getByLabel("Результат финансового расчёта")).toBeVisible();
  expect(
    baseline.scenarios.find((s) => s.name === "base")!.metrics.operating_result
      .value,
  ).toBe("285000.00");
  await page.getByLabel("Аренда", { exact: true }).fill("100000");
  const recalcResponse = page.waitForResponse((r) =>
    r.url().endsWith("/finance/calculate"),
  );
  await page.getByRole("button", { name: "Пересчитать модель →" }).click();
  const updatedResponse = await recalcResponse;
  expect(updatedResponse.ok()).toBe(true);
  const updated = (await updatedResponse.json()) as Schemas["FinanceResult"];
  expect(
    updated.scenarios.find((s) => s.name === "base")!.metrics.operating_result
      .value,
  ).toBe("265000.00");
  // Collapse inputs for a readable result screenshot, preserving the editable controls.
  await page.locator(".assumptions>summary").click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${directory}/BA-010-finance.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `${directory}/BA-010-mobile.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.getByRole("button", { name: "◇ Продукты ВТБ" }).click();
  await expect(page.getByText("Демо-каталог", { exact: true })).toBeVisible();
  await page
    .getByLabel("Стадия бизнеса", { exact: true })
    .selectOption("preparing");
  await page
    .getByLabel("Регистрация бизнеса", { exact: true })
    .selectOption("ip");
  await page
    .getByLabel("Канал продаж", { exact: true })
    .selectOption("offline");
  await page
    .getByLabel("Нужен расчётный счёт", { exact: true })
    .selectOption("true");
  await page
    .getByLabel("Планируете принимать оплату картами", { exact: true })
    .selectOption("true");
  await page
    .getByLabel("Нужна дебетовая карта для расходов", { exact: true })
    .selectOption("true");
  await page
    .getByLabel("Интересует информация о финансировании", { exact: true })
    .selectOption("false");
  const matchResponse = page.waitForResponse((r) =>
    r.url().endsWith("/bank-products/matches"),
  );
  await page
    .getByRole("button", { name: "Подобрать по потребностям →" })
    .click();
  const matchHttp = await matchResponse;
  expect(matchHttp.ok()).toBe(true);
  const bank = (await matchHttp.json()) as Schemas["MatchResult"];
  expect(bank.recommended_ids).toEqual([]);
  expect(bank.demonstration_ids).toEqual([
    "vtb-business-card",
    "vtb-merchant-acquiring",
    "vtb-rko",
  ]);
  await expect(
    page.getByText("Подбор выполнен по явным правилам"),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `${directory}/BA-011-bank.png`,
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: `${directory}/BA-011-bank-mobile.png`,
    fullPage: true,
  });
  await writeFile(
    `${directory}/BA-011-verification.json`,
    JSON.stringify(
      {
        checked_at: new Date().toISOString(),
        services:
          "real Qwen/Ollama + PostGIS + finance + authenticated bank matching API; no mocks",
        catalogue_version: bank.catalogue.version,
        catalogue_fingerprint: bank.catalogue.fingerprint,
        catalogue_mode: "demonstration",
        profile_version: bank.profile_version,
        recommended_ids: bank.recommended_ids,
        demonstration_ids: bank.demonstration_ids,
        credit_decision: bank.credit_decision,
        browser_errors: errors,
      },
      null,
      2,
    ),
  );
  await page.setViewportSize({ width: 1440, height: 1050 });
  const lead = page.getByRole("region", { name: "Демонстрационная заявка" });
  await lead
    .getByRole("button", {
      name: "Отказаться: Маркетинговые рекомендации",
      exact: true,
    })
    .click();
  await expect(lead.getByText("Отказ", { exact: true })).toBeVisible();
  await lead.getByRole("checkbox", { name: /Расчётно-кассовое/ }).check();
  await lead.getByRole("checkbox", { name: /Торговый эквайринг/ }).check();
  await expect(
    lead.getByRole("button", { name: "Подготовить демо-черновик →" }),
  ).toBeDisabled();
  await lead
    .getByRole("button", {
      name: "Согласиться: Подготовка и демонстрационная передача",
      exact: true,
    })
    .click();
  const draftResponse = page.waitForResponse(
    (r) => r.url().endsWith("/leads/drafts") && r.request().method() === "POST",
  );
  await lead
    .getByRole("button", { name: "Подготовить демо-черновик →" })
    .click();
  const draftHttp = await draftResponse;
  expect(draftHttp.ok()).toBe(true);
  const draft = (await draftHttp.json()) as Schemas["LeadDraft"];
  expect(Number(draft.payload.fields.budget)).toBe(2_000_000);
  await lead.getByLabel("Я проверил все поля и выбранные продукты").check();
  await lead
    .getByRole("button", { name: "Подтвердить состав заявки", exact: true })
    .click();
  await lead
    .getByLabel(
      "Подтверждаю создание демонстрационной заявки без отправки в банк",
    )
    .check();
  await lead.scrollIntoViewIfNeeded();
  await lead.screenshot({ path: `${directory}/BA-012-preview.png` });
  const receiptResponse = page.waitForResponse((r) =>
    r.url().endsWith("/submit"),
  );
  await lead
    .getByRole("button", { name: "Создать демонстрационную заявку →" })
    .click();
  const receiptHttp = await receiptResponse;
  expect(receiptHttp.ok()).toBe(true);
  const receipt = (await receiptHttp.json()) as Schemas["LeadReceipt"];
  expect(receipt.sent_to_bank).toBe(false);
  await expect(
    lead.getByRole("heading", {
      name: "Демонстрационная заявка создана. Данные в ВТБ не отправлены",
      exact: true,
    }),
  ).toBeVisible();
  await lead
    .locator(".lead-receipt")
    .screenshot({ path: `${directory}/BA-012-receipt.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await lead.screenshot({ path: `${directory}/BA-012-mobile.png` });
  await page.reload();
  await page.getByRole("button", { name: "◇ Продукты ВТБ" }).click();
  await expect(
    page.getByRole("heading", { name: receipt.message, exact: true }),
  ).toBeVisible();
  await writeFile(
    `${directory}/BA-012-verification.json`,
    JSON.stringify(
      {
        checked_at: new Date().toISOString(),
        services:
          "real Qwen/Ollama, PostGIS, ranking, finance, catalogue, consent, mock lead; no route mocks",
        profile_version: receipt.profile_version,
        selected_product_ids: receipt.payload.products.map((p) => p.product.id),
        payload_fields: receipt.payload.fields,
        consent_versions: receipt.consents.map((c) => ({
          purpose: c.purpose,
          text_version: c.text_version,
        })),
        sent_to_bank: receipt.sent_to_bank,
        receipt_message: receipt.message,
        restored_after_reload: true,
        browser_errors: errors,
      },
      null,
      2,
    ),
  );
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.getByRole("button", { name: "⌖ Карта и локации" }).click();
  const newZonesHttp = page.waitForResponse((r) =>
    r.url().endsWith("/rankings"),
  );
  await walking
    .getByRole("button", { name: "Найти зоны во внутренней области графа" })
    .click();
  const newZonesResponse = await newZonesHttp;
  expect(newZonesResponse.ok()).toBe(true);
  const newZones = (await newZonesResponse.json()) as Ranking;
  await walking
    .getByText("Сравнить рейтинг BA-008: по прямой и по сети", { exact: true })
    .click();
  const compareHttp = page.waitForResponse((r) =>
    r.url().endsWith("/walking-rankings"),
  );
  await walking
    .getByRole("button", { name: "Сравнить сетевой рейтинг" })
    .click();
  const comparedResponse = await compareHttp;
  expect(comparedResponse.ok()).toBe(true);
  const compared =
    (await comparedResponse.json()) as Schemas["WalkingRankingResult"];
  expect(compared.baseline.request_fingerprint).toBe(
    newZones.request_fingerprint,
  );
  expect(compared.network.evaluations.some((e) => e.score !== null)).toBe(true);
  await expect(
    walking.getByRole("columnheader", { name: "По сети", exact: true }),
  ).toBeVisible();
  await walking.screenshot({
    path: "../../docs/screenshots/BA-013-network-comparison.png",
  });
  expect(errors).toEqual([]);
  await writeFile(
    `${directory}/BA-010-verification.json`,
    JSON.stringify(
      {
        checked_at: new Date().toISOString(),
        services:
          "real local Qwen/Ollama + Compose/PostGIS + finance API; no mocks",
        extraction_mode: extracted.extraction_mode,
        profile: {
          city: extracted.profile.city,
          category: extracted.profile.category,
          budget: extracted.profile.budget,
        },
        missing_fields_after_first_turn: extracted.missing_fields,
        history_after_reload: true,
        data_version: ranking.candidates.dataset.data_version,
        ranking: ranking.evaluations.map((e) => ({
          rank: e.rank,
          score: e.score,
          status: e.status,
        })),
        baseline_operating_result: baseline.scenarios.map((s) => ({
          name: s.name,
          value: s.metrics.operating_result.value,
        })),
        changed_rent: updated.request_snapshot.monthly_fixed_costs.rent.value,
        changed_base_operating_result: updated.scenarios.find(
          (s) => s.name === "base",
        )!.metrics.operating_result.value,
        browser_errors: errors,
      },
      null,
      2,
    ),
  );
});
