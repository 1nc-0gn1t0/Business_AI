import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { env } from "node:process";
import type { Conversation, Ranking, Schemas } from "../src/api";

test("U-05 real manual school: review, course finance, what-if and reload without Ollama", async ({
  page,
}) => {
  test.skip(
    env.BA_U05_REAL !== "1",
    "Requires isolated U-05 Compose, no API mocks",
  );
  const directory = "../../docs/qa/u-05";
  await mkdir(`${directory}/screenshots`, { recursive: true });
  const created = await page.request.post("/api/v1/conversations", {
    data: {},
  });
  expect(created.status()).toBe(201);
  const key = await created.json();
  const headers = { "X-Conversation-Token": key.access_token };
  expect(
    (
      await page.request.put(
        `/api/v1/conversations/${key.id}/consents/assistant`,
        {
          headers,
          data: {
            expected_revision: 0,
            text_version: "assistant-demo-v1",
            decision: "grant",
          },
        },
      )
    ).status(),
  ).toBe(200);
  const url = `/api/v2/conversations/${key.id}/industry-profile`;
  const profile = await page.request.patch(url, {
    headers,
    data: {
      expected_version: 0,
      industry: "online_school",
      updates: Object.entries({
        budget: "1500000",
        audience: "взрослые",
        format: "онлайн",
        payment_model: "за курс",
        students: 20,
      }).map(([field, value]) => ({ field, value })),
    },
  });
  expect(profile.status()).toBe(200);
  await page.addInitScript(
    ({ id, token }) =>
      sessionStorage.setItem(
        "business-ai.guest.v1",
        JSON.stringify({ id, token }),
      ),
    { id: key.id, token: key.access_token },
  );
  const errors: string[] = [],
    excludedRequests: string[] = [];
  const consoleErrors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (
      /\/api\/v1\/(geo|finance)\//.test(r.url()) ||
      r.url().endsWith("/propose")
    )
      excludedRequests.push(new URL(r.url()).pathname);
  });
  await page.goto("/#business-ai");
  await expect(
    page.getByRole("heading", { name: "Ваш проект", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Сколько может приносить ваш бизнес?" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Модель оплаты обучения" })
    .selectOption("course");
  const values: Record<string, string> = {
    students: "20",
    student_capacity: "30",
    tuition: "10000",
    course_months: "3",
    variable_per_student: "1000",
    fee_ratio: "0.05",
    teachers: "60000",
    platform: "10000",
    marketing: "30000",
    other_fixed: "50000",
  };
  const financialUrl = url.replace("industry-profile", "financial-scenarios");
  const view = (await (
    await page.request.get(financialUrl, { headers })
  ).json()) as Schemas["FinancialView"];
  for (const field of view.configuration.parameters) {
    await page
      .getByRole("textbox", { name: field.label, exact: true })
      .fill(values[field.id]);
    await page
      .getByRole("combobox", {
        name: `${field.label}: происхождение`,
        exact: true,
      })
      .selectOption("user_assumption");
  }
  for (const [label, low, high] of [
    ["Платящие ученики", "10", "30"],
    ["Цена за выбранный период оплаты", "8000", "12000"],
  ]) {
    const fieldset = page.locator(".financial-input").filter({
      has: page.getByRole("textbox", { name: label, exact: true }),
    });
    await fieldset.getByText("Сценарный диапазон", { exact: true }).click();
    await page
      .getByRole("textbox", { name: `${label}: минимум`, exact: true })
      .fill(low);
    await page
      .getByRole("textbox", { name: `${label}: максимум`, exact: true })
      .fill(high);
  }
  await page
    .getByRole("button", { name: "Сохранить вводные для проверки" })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "Проверено: Платящие ученики" }),
  ).toBeVisible();
  for (const checkbox of await page.getByRole("checkbox").all())
    await checkbox.check();
  await page
    .getByRole("button", { name: "Использовать выбранные значения" })
    .click();
  const started = Date.now();
  const waiting = page.waitForResponse(
    (r) => r.url().endsWith("/calculate") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Рассчитать три сценария" }).click();
  const response = await waiting;
  expect(response.status()).toBe(200);
  const result = (await response.json()) as Schemas["FinancialView"];
  expect(result.result!.result.scenarios[1].operating_result).toBe(
    "-280000.00",
  );
  expect(result.result!.result.scenarios[1].period).toBe("course_cohort");
  expect(result.result!.result.contains_assumptions).toBe(true);
  expect(
    result.result!.result.scenarios.map((s) => s.operating_result),
  ).toEqual(["-384000.00", "-280000.00", "-138000.00"]);
  const elapsed = Date.now() - started;
  await page
    .getByText("Ввести или проверить параметры", { exact: true })
    .click();
  await page
    .getByRole("textbox", {
      name: "Постоянные расходы на преподавателей",
      exact: true,
    })
    .fill("70000");
  const previewing = page.waitForResponse((r) => r.url().endsWith("/what-if"));
  await page.getByRole("button", { name: "Проверить без сохранения" }).click();
  const preview = (await (await previewing).json()) as Schemas["WhatIfResult"];
  expect(preview.persisted).toBe(false);
  expect(preview.result.scenarios[1].operating_result).toBe("-310000.00");
  const beforeReload = (await (
    await page.request.get(financialUrl, { headers })
  ).json()) as Schemas["FinancialView"];
  expect(beforeReload.document).toEqual(result.document);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Базовый" })).toBeVisible();
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 950 });
    expect(
      await page.locator("body").evaluate((el) => el.scrollWidth <= innerWidth),
    ).toBe(true);
    await page.screenshot({
      path: `${directory}/screenshots/real-school-${width}.png`,
      fullPage: true,
    });
  }
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать сценарный JSON" }).click();
  expect(await (await download).failure()).toBeNull();
  await (await download).saveAs(`${directory}/real-school-scenarios.json`);
  expect(errors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(excludedRequests).toEqual([]);
  await writeFile(
    `${directory}/browser-real-manual.json`,
    JSON.stringify(
      {
        mode: "Built Compose/API/PostGIS; manual scenario inputs; no mocks; no Ollama calls",
        calculation_http_ms: elapsed,
        base_operating_result: "-280000.00",
        preview_operating_result: "-310000.00",
        what_if_persisted: false,
        period: "course_cohort",
        months: 3,
        browser_errors: errors,
        console_errors: consoleErrors,
        scenarios: result.result!.result.scenarios.map(
          (s) => s.operating_result,
        ),
        excluded_requests: excludedRequests,
        widths: [1440, 768, 390],
        download: "real-school-scenarios.json",
      },
      null,
      2,
    ),
  );
});

test("U-04 real online school: Qwen, review, no-map, reload and JSON", async ({
  page,
}) => {
  test.skip(
    env.BA_U04_REAL !== "1",
    "Requires isolated U-04 Compose with real local Qwen",
  );
  const directory = "../../docs/qa/u-04/screenshots";
  await mkdir(directory, { recursive: true });
  const errors: string[] = [];
  const geographicRequests: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (
      r.url().includes("/api/v1/geo/") ||
      r.url().includes("/api/v1/finance/")
    )
      geographicRequests.push(new URL(r.url()).pathname);
  });
  await page.goto("/#business-ai");
  await page
    .getByLabel("Сообщение помощнику")
    .fill(
      "Хочу открыть онлайн-школу программирования. Бюджет 1,5 миллиона рублей.",
    );
  await page.getByLabel("Отправить сообщение").click();
  await page.getByLabel("Согласен на использование ассистента").check();
  const started = Date.now();
  const responsePromise = page.waitForResponse(
    (r) => r.url().includes("/industry-profile/messages"),
    { timeout: 180000 },
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Продолжить", exact: true })
    .click();
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  const first = (await response.json()) as Schemas["UniversalView"];
  expect(first.profile.industry).toBe("online_school");
  expect(first.extraction).toBe("ollama");
  const classificationMs = Date.now() - started;
  await page
    .getByRole("button", { name: "Проверить параметры проекта" })
    .click();
  await page
    .getByRole("button", { name: "Изменить параметры", exact: true })
    .click();
  await page
    .getByLabel("Аудитория", { exact: true })
    .fill("Взрослые начинающие");
  await page.getByLabel("Формат", { exact: true }).fill("Онлайн-занятия");
  await page.getByLabel("Модель оплаты", { exact: true }).fill("Оплата курса");
  await page.getByLabel("Число учеников", { exact: true }).fill("20");
  await page
    .getByRole("button", { name: "Сохранить параметры", exact: true })
    .click();
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Вводные готовы" }),
  ).toBeVisible();
  await expect(page.getByText(/без карты/)).toBeVisible();
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `${directory}/real-school-${width}.png`,
      fullPage: true,
    });
  }
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Вводные готовы" }),
  ).toBeVisible();
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать вводные JSON" }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe("business-inputs.json");
  await page.getByRole("button", { name: "Изменить проект" }).click();
  await expect(
    page.getByRole("heading", { name: "Ваш проект", exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
  expect(geographicRequests).toEqual([]);
  await writeFile(
    "../../docs/qa/u-04/browser-real.json",
    JSON.stringify(
      {
        scope:
          "real built web/API/PostGIS + local Qwen in isolated Compose; no mocks",
        classificationMs,
        industry: first.profile.industry,
        extraction: first.extraction,
        reload: true,
        jsonDownload: true,
        errors,
        geographicRequests,
      },
      null,
      2,
    ),
  );
});

// Opt-in real services. No routes, model mocks, traces, credentials or prompts in artifacts.
test("DESIGN03FU real coffee: idea → Qwen → profile → PostGIS → finance → bank → PDF/JSON", async ({
  page,
}) => {
  page.setDefaultTimeout(20_000);
  const directory = env.BA010_ARTIFACT_DIR || "../../docs/qa/design-03-fu";
  const downloads =
    env.BA_DESIGN02_DOWNLOAD_DIR || "test-results/design03fu-downloads";
  await mkdir(directory, { recursive: true });
  await mkdir(downloads, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const timings: { step: string; ms: number }[] = [];
  const shot = async (name: string) => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.evaluate(async () => {
      const scroll = document.querySelector(".chat-scroll");
      if (scroll) scroll.scrollTop = scroll.scrollHeight;
      await Promise.all(
        document
          .getAnimations()
          .filter((a) => Number(a.effect?.getComputedTiming().endTime) <= 1200)
          .map((a) => a.finished.catch(() => {})),
      );
    });
    await page.screenshot({ path: `${directory}/${name}.png`, fullPage: true });
  };
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Ваш бизнес/ })).toBeVisible();
  await shot("01-landing-desktop");
  await page
    .locator(".vi-dock")
    .screenshot({ path: `${directory}/02-three-bubbles.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  await shot("10-landing-mobile");
  await page.getByRole("button", { name: "Познакомьтесь с Ви" }).click();
  await shot("11-welcome-mobile");
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 768, height: 1000 });
  await shot("13-landing-tablet");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Познакомьтесь с Ви" }).hover();
  await shot("03-vi-hover");
  await page.getByRole("button", { name: "Познакомьтесь с Ви" }).click();
  await shot("04-welcome-desktop");
  await page.getByRole("button", { name: "Начать с Ви" }).click();
  await expect(
    page.getByRole("heading", { name: "Какой бизнес вы хотите открыть?" }),
  ).toBeVisible();
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await shot("01-start-desktop");
  await page
    .getByLabel("Сообщение помощнику")
    .fill("Хочу открыть кофейню в Казани");
  await page.getByLabel("Отправить сообщение").click();
  await page.getByLabel("Согласен на использование ассистента").check();
  let view: Conversation;
  async function turn(text: string | undefined, first = false) {
    const start = Date.now();
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/messages") && r.request().method() === "POST",
      { timeout: 190_000 },
    );
    if (first)
      await page
        .getByRole("dialog")
        .getByRole("button", { name: "Продолжить", exact: true })
        .click();
    else {
      await page.getByLabel("Сообщение помощнику").fill(text!);
      await page.getByLabel("Отправить сообщение").click();
    }
    if (first) {
      await expect(page.locator(".vi-chat")).toHaveAttribute(
        "data-emotion",
        "working",
      );
      await shot("06-qwen-waiting");
    }
    const result = await response;
    expect(result.status()).toBe(200);
    view = (await result.json()) as Conversation;
    expect(view.extraction_mode).toBe("ollama");
    if (view.missing_fields.length) {
      await expect(page.getByLabel("Сообщение помощнику")).toBeEnabled();
      await expect(page.getByRole("log")).toContainText(view.assistant_message);
    } else
      await expect(
        page.getByRole("heading", { name: "Всё верно?" }),
      ).toBeVisible();
    timings.push({
      step: `qwen-turn-${timings.length + 1}`,
      ms: Date.now() - start,
    });
    return view;
  }
  view = await turn(undefined, true);
  expect(view.profile.city).toBe("Казань");
  expect(view.profile.category).toContain("кофейн");
  expect(view.assistant_message).toBe("Какой у вас бюджет в рублях?");
  view = await turn("2 миллиона рублей");
  expect(Number(view.profile.budget)).toBe(2_000_000);
  expect(view.assistant_message).toBe("Какой формат бизнеса рассматриваете?");
  view = await turn("Навынос");
  expect(view.profile.preferences.format).toBeTruthy();
  await shot("05-chat-avatar");
  await page.setViewportSize({ width: 768, height: 1000 });
  await shot("08-chat-tablet");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await shot("12-chat-mobile");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  view = await turn("Свои средства");
  expect(view.profile.funding).toBe("own_funds");
  expect(view.missing_fields).toEqual([]);
  await expect(page.getByRole("heading", { name: "Всё верно?" })).toBeVisible();
  await shot("03-confirmation-desktop");
  const confirming = page.waitForResponse((r) =>
    r.url().endsWith("/profile/confirm"),
  );
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  const confirmed = await confirming;
  expect(confirmed.status()).toBe(200);
  const confirmedView = (await confirmed.json()) as Conversation;
  expect(confirmedView.profile.confirmation_state).toBe("confirmed");
  const rankingResponse = page.waitForResponse((r) =>
    r.url().endsWith("/rankings"),
  );
  const searchStarted = page.waitForRequest((r) =>
    r.url().endsWith("/rankings"),
  );
  await page
    .getByRole("button", { name: "Найти локации", exact: true })
    .click();
  await searchStarted;
  await expect(page.locator(".locations .vi-status")).toHaveAttribute(
    "data-emotion",
    "search",
  );
  await page.screenshot({
    path: `${directory}/07-location-search.png`,
    fullPage: true,
  });
  const ranked = await rankingResponse;
  expect(ranked.status()).toBe(200);
  const geo = (await ranked.json()) as Ranking;
  expect(geo.candidates.features.length).toBeGreaterThan(1);
  expect(geo.evaluations.some((e) => e.score !== null)).toBe(true);
  await page
    .getByRole("button", { name: "Выбрать зону на карте: 2", exact: true })
    .click();
  await expect(page.locator(".zone-card").nth(1)).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.locator(".zone-card").first().click();
  await expect(
    page.getByRole("button", { name: "Выбрать зону на карте: 1", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await shot("04-location-desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  await shot("10-location-mobile");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Продолжить к расчётам" }).click();
  const financialResponse = page.waitForResponse((r) =>
    r.url().endsWith("/finance/calculate"),
  );
  await page.getByRole("button", { name: "Рассчитать сценарии" }).click();
  const first = await financialResponse;
  expect(first.status()).toBe(200);
  const finance = (await first.json()) as Schemas["FinanceResult"];
  expect(finance.scenarios).toHaveLength(3);
  const base = finance.scenarios.find((s) => s.name === "base")!;
  expect(base.metrics.operating_result.value).toBe("285000.00");
  await shot("08-finance-idea");
  await page.getByLabel("Аренда", { exact: true }).fill("90000");
  await expect(
    page.getByRole("button", { name: "Продолжить", exact: true }),
  ).toBeDisabled();
  const recalculating = page.waitForResponse((r) =>
    r.url().endsWith("/finance/calculate"),
  );
  await page.getByRole("button", { name: "Пересчитать модель →" }).click();
  const second = await recalculating;
  expect(second.status()).toBe(200);
  const recalculated = (await second.json()) as Schemas["FinanceResult"];
  expect(
    recalculated.scenarios.find((s) => s.name === "base")!.metrics
      .operating_result.value,
  ).toBe("275000.00");
  await shot("11-finance-recalculated");
  await page.setViewportSize({ width: 390, height: 844 });
  await shot("12-finance-mobile");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await page.getByRole("button", { name: "Да", exact: true }).click();
  await page.getByRole("button", { name: "ИП", exact: true }).click();
  await page.getByRole("button", { name: "Да", exact: true }).click();
  await page
    .getByRole("button", { name: "Физическая точка", exact: true })
    .click();
  await page.getByRole("button", { name: "Нет", exact: true }).click();
  const matching = page.waitForResponse((r) =>
    r.url().endsWith("/bank-products/matches"),
  );
  await page
    .getByRole("button", { name: "Подобрать по потребностям →", exact: true })
    .click();
  const bankResult = await matching;
  expect(bankResult.status()).toBe(200);
  const bank = (await bankResult.json()) as Schemas["MatchResult"];
  expect(bank.credit_decision).toBe("not_assessed");
  await expect(
    page.getByRole("heading", { name: "Возможности для вашего проекта" }),
  ).toBeVisible();
  await shot("06-banking-desktop");
  await page.getByRole("button", { name: "К результату", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ваш бизнес-план готов" }),
  ).toBeVisible();
  await shot("07-summary-desktop");
  let reportId = "";
  for (const format of ["pdf", "json"]) {
    const waiting = page.waitForEvent("download");
    await page
      .getByRole("button", {
        name: `Скачать ${format.toUpperCase()}`,
        exact: true,
      })
      .click();
    const download = await waiting;
    expect(await download.failure()).toBeNull();
    const id = download
      .suggestedFilename()
      .replace(/^BusinessAI-report-/, "")
      .replace(/\.(pdf|json)$/, "");
    if (reportId) expect(id).toBe(reportId);
    reportId = id;
    await download.saveAs(`${downloads}/DESIGN03FU-report.${format}`);
  }
  await expect(page.locator(".report-export .vi-status")).toHaveAttribute(
    "data-emotion",
    "success",
  );
  await shot("09-report-ready");
  await page.setViewportSize({ width: 390, height: 844 });
  await shot("16-summary-mobile");
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
  expect(page.url()).not.toContain("token");
  expect(errors).toEqual([]);
  await writeFile(
    `${directory}/live-evidence.json`,
    JSON.stringify(
      {
        mode: "real API/Ollama/PostGIS, no route mocks",
        base_main: "718bcf936966fe5465ea67ca4e0806bc0cf16372",
        model: "qwen3:4b-instruct-2507-q4_K_M",
        profile_version: confirmedView.version,
        qwen_turns: timings,
        zone_count: geo.candidates.features.length,
        data_version: geo.candidates.dataset.data_version,
        finance_algorithm: finance.algorithm_version,
        base_before: base.metrics.operating_result.value,
        base_after: recalculated.scenarios.find((s) => s.name === "base")!
          .metrics.operating_result.value,
        catalogue_version: bank.catalogue.version,
        demonstration_matches: bank.demonstration_ids.length,
        credit_decision: bank.credit_decision,
        downloads: ["pdf", "json"],
        browser_errors: errors,
      },
      null,
      2,
    ),
  );
});

for (const scenario of [
  {
    name: "bakery-low-budget",
    prompt: "Хочу открыть пекарню в Казани, бюджет 500000 рублей",
    city: "Казань",
    category: "пекарня",
    budget: 500000,
    covered: true,
  },
  {
    name: "garage-uncovered-city",
    prompt: "Хочу открыть автосервис в Самаре, бюджет 10000000 рублей",
    city: "Самара",
    category: "автосервис",
    budget: 10000000,
    covered: false,
  },
])
  test(`BA016 real ${scenario.name}: extraction and honest city coverage`, async ({
    page,
  }) => {
    await page.goto("/#business-ai");
    await page.getByLabel("Сообщение помощнику").fill(scenario.prompt);
    await page.getByLabel("Отправить сообщение").click();
    await page.getByLabel("Согласен на использование ассистента").check();
    const turn = page.waitForResponse(
      (r) => r.url().endsWith("/messages") && r.request().method() === "POST",
      { timeout: 190000 },
    );
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Продолжить", exact: true })
      .click();
    const response = await turn;
    expect(response.status()).toBe(200);
    const view = (await response.json()) as Conversation;
    expect(view.extraction_mode).toBe("ollama");
    expect(view.profile.city).toBe(scenario.city);
    expect(view.profile.category).toBe(scenario.category);
    expect(Number(view.profile.budget)).toBe(scenario.budget);
    await page
      .getByRole("button", { name: "Проверить параметры проекта" })
      .click();
    await page.getByRole("button", { name: "Изменить", exact: true }).click();
    await page
      .getByLabel("Формат", { exact: true })
      .fill("отдельное помещение");
    await page.getByLabel("Источник средств").selectOption("own_funds");
    await page.getByRole("button", { name: "Сохранить профиль" }).click();
    await page.getByRole("button", { name: "Продолжить", exact: true }).click();
    const ranked = page.waitForResponse((r) => r.url().endsWith("/rankings"));
    await page.getByRole("button", { name: "Найти локации" }).click();
    const rank = await ranked;
    expect(rank.status()).toBe(200);
    const geo = (await rank.json()) as Ranking;
    expect(geo.candidates.features.length > 0).toBe(scenario.covered);
    if (!scenario.covered)
      await expect(
        page.getByRole("button", { name: "Продолжить к расчётам" }),
      ).toBeDisabled();
  });
