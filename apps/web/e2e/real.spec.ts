import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { env } from "node:process";
import type { Conversation, Ranking, Schemas } from "../src/api";

// Opt-in real services. No routes, model mocks, traces, credentials or prompts in artifacts.
test("DESIGN03 real coffee: idea → Qwen → profile → PostGIS → finance → bank → PDF/JSON", async ({
  page,
}) => {
  page.setDefaultTimeout(20_000);
  const directory = env.BA010_ARTIFACT_DIR || "../../docs/qa/design-03";
  const downloads =
    env.BA_DESIGN02_DOWNLOAD_DIR || "test-results/design03-downloads";
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
          .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
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
    await download.saveAs(`${downloads}/DESIGN03-report.${format}`);
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
        base_main: "45c6a0d2c35846ffc7271cfd6d8a06eb967a2539",
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
