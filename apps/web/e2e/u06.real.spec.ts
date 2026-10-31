import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { env } from "node:process";
import type { Schemas } from "../src/api";
test.use({ actionTimeout: 30000 });

const cases = [
  {
    model: "auto_repair",
    idea: "Хочу открыть автосервис в Москве. Бюджет 8 миллионов рублей, четыре поста.",
    profile: {
      city: "Москва",
      budget: "8000000",
      specialization: "ремонт автомобилей",
      service_bays: 4,
      physical_premises: true,
    },
    inputs: {
      service_bays: "4",
      working_days: "25",
      orders_per_bay: "2",
      rent: "100000",
      payroll: "200000",
      utilities: "20000",
      marketing: "30000",
      other_fixed: "50000",
    },
  },
  {
    model: "online_school",
    idea: "Хочу открыть онлайн-школу программирования. Бюджет 1500000 рублей.",
    profile: {
      budget: "1500000",
      audience: "взрослые",
      format: "онлайн",
      payment_model: "помесячно",
      students: 20,
    },
    inputs: {
      student_capacity: "100",
      teachers: "60000",
      platform: "10000",
      marketing: "30000",
      other_fixed: "10000",
    },
  },
  {
    model: "generic",
    idea: "Хочу открыть бизнес необычного формата, для которого нет отраслевого шаблона: сервис настройки робототеплиц.",
    profile: {
      budget: "2000000",
      business_model: "сервис",
      physical_premises: false,
      audience: "фермеры",
      revenue_streams: "обслуживание робототеплицы",
    },
    inputs: {
      unit_sales: "100",
      unit_price: "2000",
      variable_per_unit: "500",
      rent: "0",
      payroll: "0",
      utilities: "0",
      marketing: "0",
      other_fixed: "50000",
    },
  },
] as const;

for (const scenario of cases)
  test(`U-06 real ${scenario.model}: adaptive route and integrated result`, async ({
    page,
  }) => {
    test.skip(
      env.BA_U06_REAL !== "1",
      "Requires isolated U-06 API, PostGIS and existing Qwen",
    );
    const directory = `../../docs/qa/u-06/${scenario.model}`;
    await mkdir(directory, { recursive: true });
    const started = Date.now();
    const pageErrors: string[] = [],
      consoleErrors: string[] = [],
      geoRequests: string[] = [];
    let proposalRequests = 0;
    page.on("pageerror", (e) => pageErrors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") consoleErrors.push(m.text());
    });
    page.on("request", (r) => {
      if (/\/api\/v1\/(geo|finance)\//.test(r.url()))
        geoRequests.push(new URL(r.url()).pathname);
      if (r.url().endsWith("/propose")) proposalRequests++;
    });
    await page.goto("/#business-ai");
    await page.getByLabel("Сообщение помощнику").fill(scenario.idea);
    await page.getByLabel("Отправить сообщение").click();
    await page.getByLabel("Согласен на использование ассистента").check();
    const classified = page.waitForResponse(
      (r) => r.url().endsWith("/industry-profile/messages"),
      { timeout: 180000 },
    );
    const classificationStarted = Date.now();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Продолжить", exact: true })
      .click();
    const response = await classified;
    expect(response.status()).toBe(200);
    const classificationMs = Date.now() - classificationStarted;
    const classification = (await response.json()) as Schemas["UniversalView"];
    expect(classification.extraction).toBe("ollama");
    expect(classification.profile.industry).toBe(scenario.model);
    if (
      await page
        .getByRole("button", { name: "Проверить параметры проекта" })
        .isVisible()
    )
      await page
        .getByRole("button", { name: "Проверить параметры проекта" })
        .click();
    await expect(
      page.getByRole("heading", { name: "Ваш проект", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Изменить параметры", exact: true })
      .click();
    for (const [key, value] of Object.entries(scenario.profile)) {
      const control = page.locator(`.profile-form [name="${key}"]`);
      if (await control.evaluate((el) => el.tagName === "SELECT"))
        await control.selectOption(String(value));
      else await control.fill(String(value));
    }
    let saved = page.waitForResponse(
      (r) =>
        r.url().endsWith("industry-profile") &&
        r.request().method() === "PATCH",
    );
    await page
      .getByRole("button", { name: "Сохранить параметры", exact: true })
      .click();
    expect((await saved).status()).toBe(200);
    await page.getByRole("button", { name: "Продолжить", exact: true }).click();
    await expect(
      page.getByRole("heading", {
        name: "Сколько может приносить ваш бизнес?",
      }),
    ).toBeVisible();
    const key = (await page.evaluate(() =>
      JSON.parse(sessionStorage.getItem("business-ai.guest.v1")!),
    )) as { id: string; token: string };
    const headers = { "X-Conversation-Token": key.token };
    const base = `/api/v2/conversations/${key.id}`;
    const finance = base + "/financial-scenarios";
    let view = (await (
      await page.request.get(finance, { headers })
    ).json()) as Schemas["FinancialView"];
    if (scenario.model === "online_school")
      await page.getByLabel("Модель оплаты обучения").selectOption("monthly");
    const inputSummary = page.getByText("Ввести или проверить параметры", {
      exact: true,
    });
    if (
      !(await inputSummary.evaluate(
        (el) => (el.parentElement as HTMLDetailsElement).open,
      ))
    )
      await inputSummary.click();
    for (const [id, value] of Object.entries(scenario.inputs)) {
      const label = view.configuration.parameters.find(
        (p) => p.id === id,
      )!.label;
      await page.getByRole("textbox", { name: label, exact: true }).fill(value);
      await page
        .getByLabel(`${label}: происхождение`, { exact: true })
        .selectOption("user_assumption");
    }
    saved = page.waitForResponse(
      (r) =>
        r.url().endsWith("financial-scenarios") &&
        r.request().method() === "PATCH",
    );
    await page
      .getByRole("button", { name: "Сохранить вводные для проверки" })
      .click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByRole("checkbox").first()).toBeEnabled();
    for (const checkbox of await page.getByRole("checkbox").all())
      await checkbox.check();
    saved = page.waitForResponse((r) => r.url().endsWith("/review"));
    await page
      .getByRole("button", { name: "Использовать выбранные значения" })
      .click();
    expect((await saved).status()).toBe(200);
    let proposalMs: number | null = null;
    if (scenario.model !== "generic") {
      saved = page.waitForResponse((r) => r.url().endsWith("/propose"), {
        timeout: 180000,
      });
      const inferenceStarted = Date.now();
      await page
        .getByRole("button", { name: "Предложить допущения с Ви" })
        .click();
      await expect(
        page.getByText("Готовлю сценарные предположения…", { exact: true }),
      ).toBeVisible();
      await page.screenshot({
        path: `${directory}/thinking.png`,
        fullPage: true,
      });
      const proposal = await saved;
      expect(proposal.status()).toBe(200);
      view = (await proposal.json()) as Schemas["FinancialView"];
      proposalMs = Date.now() - inferenceStarted;
      expect(
        Object.values(view.document.entries).some(
          (e) => e.method === "qwen_exploratory",
        ),
      ).toBe(true);
      for (const entry of Object.values(view.document.entries).filter(
        (e) => e.method === "qwen_exploratory",
      )) {
        expect(entry.review).toBe("proposed");
        expect(entry.source.origin).toBe("synthetic");
      }
      await page.screenshot({
        path: `${directory}/review.png`,
        fullPage: true,
      });
      if (scenario.model === "online_school") {
        const label = view.configuration.parameters.find(
          (p) => p.id === "tuition",
        )!.label;
        await page
          .getByRole("checkbox", { name: `Проверено: ${label}`, exact: true })
          .check();
        saved = page.waitForResponse((r) => r.url().endsWith("/review"));
        await page.getByRole("button", { name: "Отклонить выбранные" }).click();
        expect((await saved).status()).toBe(200);
        await page
          .getByRole("textbox", { name: label, exact: true })
          .fill("6500");
        const field = page.locator(".financial-input").filter({
          has: page.getByRole("textbox", { name: label, exact: true }),
        });
        await field.getByText("Сценарный диапазон", { exact: true }).click();
        await page
          .getByRole("textbox", { name: `${label}: минимум`, exact: true })
          .fill("6000");
        await page
          .getByRole("textbox", { name: `${label}: максимум`, exact: true })
          .fill("7500");
        saved = page.waitForResponse(
          (r) =>
            r.url().endsWith("financial-scenarios") &&
            r.request().method() === "PATCH",
        );
        await page
          .getByRole("button", { name: "Сохранить вводные для проверки" })
          .click();
        expect((await saved).status()).toBe(200);
      }
      await expect(page.getByRole("checkbox").first()).toBeEnabled();
      for (const checkbox of await page.getByRole("checkbox").all())
        await checkbox.check();
      saved = page.waitForResponse((r) => r.url().endsWith("/review"));
      await page
        .getByRole("button", { name: "Использовать выбранные значения" })
        .click();
      expect((await saved).status()).toBe(200);
    }
    saved = page.waitForResponse((r) => r.url().endsWith("/calculate"));
    const calculationStarted = Date.now();
    await page.getByRole("button", { name: "Рассчитать три сценария" }).click();
    view = (await (await saved).json()) as Schemas["FinancialView"];
    const calculationMs = Date.now() - calculationStarted;
    expect(view.result?.result.status).toBe("calculated");
    await page
      .getByRole("button", { name: "Продолжить к возможностям банка" })
      .click();
    // Explicit user choices; existing banking rules execute without credit scoring.
    for (const answer of [
      "Да",
      "Пока не зарегистрирован",
      "Нет",
      "Да",
      scenario.model === "auto_repair" ? "Физическая точка" : "Онлайн",
      "Нет",
    ]) {
      await page.getByRole("button", { name: answer, exact: true }).click();
    }
    saved = page.waitForResponse((r) =>
      r.url().endsWith("/bank-products/matches"),
    );
    await page
      .getByRole("button", { name: "Подобрать по потребностям →", exact: true })
      .first()
      .click();
    const bank = (await (await saved).json()) as Schemas["MatchResult"];
    expect(bank.status).toBe("evaluated");
    expect(bank.credit_decision).toBe("not_assessed");
    await expect(
      page.getByText(/Для новых отраслей mock-заявка пока недоступна/),
    ).toBeVisible();
    await page
      .getByRole("button", { name: /К результату|Продолжить без подбора/ })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Предварительный результат",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Базовый", exact: true }),
    ).toBeVisible();
    const report = (await (
      await page.request.get(base + "/analysis-result", { headers })
    ).json()) as Schemas["AnalysisResult"];
    expect(report.financial).toEqual(view.result);
    expect(report.state).toBe(
      scenario.model === "online_school" ? "completed" : "partial",
    );
    if (scenario.model === "auto_repair") {
      expect(
        report.plan.capabilities.find((c) => c.id === "geo.analysis")?.status,
      ).toBe("unsupported");
      expect(
        report.plan.coverage?.assessments.every(
          (a) => a.local_status !== "available",
        ),
      ).toBe(true);
    }
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 950 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: `${directory}/result-${width}.png`,
        fullPage: true,
      });
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    expect(
      await page.evaluate(
        () => matchMedia("(prefers-reduced-motion: reduce)").matches,
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Скачать итоговый JSON" }).focus();
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.tagName)).toBe(
      "BUTTON",
    );
    const beforeReload = Date.now();
    await page.reload();
    await expect(
      page.getByRole("heading", {
        name: "Предварительный результат",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Базовый", exact: true }),
    ).toBeVisible();
    const reloadMs = Date.now() - beforeReload;
    await page.goBack();
    await expect(
      page.getByRole("heading", {
        name: "Что поможет вашему бизнесу?",
        exact: true,
      }),
    ).toBeVisible();
    await page.goForward();
    await expect(
      page.getByRole("heading", {
        name: "Предварительный результат",
        exact: true,
      }),
    ).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Скачать итоговый JSON" }).click();
    await (await download).saveAs(`${directory}/result.json`);
    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
    expect(geoRequests).toEqual([]);
    expect(proposalRequests).toBe(scenario.model === "generic" ? 0 : 1);
    await writeFile(
      `${directory}/evidence.json`,
      JSON.stringify(
        {
          model: "qwen3:4b-instruct-2507-q4_K_M",
          industry: scenario.model,
          classificationMs,
          proposalMs,
          calculationMs,
          reloadMs,
          totalMs: Date.now() - started,
          proposalRequests,
          extraction: classification.extraction,
          state: report.state,
          financial: report.financial?.result.scenarios.map((s) => ({
            name: s.name,
            operating_result: s.operating_result,
          })),
          reviewedAI: Object.values(view.document.entries)
            .filter((e) => e.method === "qwen_exploratory")
            .map((e) => ({
              epistemic: e.epistemic,
              origin: e.source.origin,
              review: e.review,
            })),
          bankCreditDecision: bank.credit_decision,
          pageErrors,
          consoleErrors,
          geoRequests,
          correction:
            scenario.model === "online_school"
              ? "Rejected tuition, manually corrected 6500 (6000…7500), reviewed again"
              : null,
          fixture:
            "Manual scenario inputs are synthetic, actual Qwen and deterministic services, no network mocks",
        },
        null,
        2,
      ),
    );
  });

test("U-06 resilience: real Qwen cancel, in-flight reload, offline recovery, stale and revoke", async ({
  page,
  context,
}) => {
  test.skip(
    env.BA_U06_RESILIENCE !== "1",
    "Requires isolated QA and real existing Qwen",
  );
  const directory = "../../docs/qa/u-06/resilience";
  await mkdir(directory, { recursive: true });
  const pageErrors: string[] = [],
    expectedConsoleErrors: string[] = [];
  let proposalRequests = 0;
  page.on("pageerror", (e) => pageErrors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") expectedConsoleErrors.push(m.text());
  });
  page.on("request", (r) => {
    if (r.url().endsWith("/propose")) proposalRequests++;
  });
  const created = await page.request.post("/api/v1/conversations", {
    data: {},
  });
  expect(created.status()).toBe(201);
  const key = await created.json();
  const headers = { "X-Conversation-Token": key.access_token };
  const legacy = `/api/v1/conversations/${key.id}`,
    base = `/api/v2/conversations/${key.id}`;
  expect(
    (
      await page.request.put(legacy + "/consents/assistant", {
        headers,
        data: {
          expected_revision: 0,
          text_version: "assistant-demo-v1",
          decision: "grant",
        },
      })
    ).status(),
  ).toBe(200);
  expect(
    (
      await page.request.patch(base + "/industry-profile", {
        headers,
        data: {
          expected_version: 0,
          industry: "online_school",
          updates: Object.entries({
            budget: "1500000",
            audience: "взрослые",
            format: "онлайн",
            payment_model: "помесячно",
            students: 20,
          }).map(([field, value]) => ({ field, value })),
        },
      })
    ).status(),
  ).toBe(200);
  expect(
    (
      await page.request.post(base + "/industry-profile/confirm", {
        headers,
        data: { expected_version: 1 },
      })
    ).status(),
  ).toBe(200);
  const finance = base + "/financial-scenarios";
  let view = (await (
    await page.request.get(finance, { headers })
  ).json()) as Schemas["FinancialView"];
  const command = () => ({
    request_id: crypto.randomUUID(),
    expected_profile_revision: view.document.profile_revision,
    expected_input_revision: view.document.revision,
  });
  const seed = {
    student_capacity: "100",
    teachers: "200000",
    platform: "10000",
    marketing: "30000",
    other_fixed: "10000",
  };
  view = (await (
    await page.request.patch(finance, {
      headers,
      data: {
        ...command(),
        billing_model: "monthly",
        updates: Object.entries(seed).map(([parameter, value]) => ({
          parameter,
          unit: view.configuration.parameters.find((p) => p.id === parameter)!
            .unit,
          base: value,
          low: value,
          high: value,
          kind: "user_assumption",
          basis: "Explicit synthetic resilience fixture",
        })),
      },
    })
  ).json()) as Schemas["FinancialView"];
  view = (await (
    await page.request.post(finance + "/review", {
      headers,
      data: { ...command(), confirm: Object.keys(view.document.entries) },
    })
  ).json()) as Schemas["FinancialView"];
  await page.addInitScript(
    ({ id, token }) =>
      sessionStorage.setItem(
        "business-ai.guest.v1",
        JSON.stringify({ id, token }),
      ),
    { id: key.id, token: key.access_token },
  );
  await page.goto("/#business-ai");
  await expect(
    page.getByRole("heading", { name: "Сколько может приносить ваш бизнес?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Предложить допущения с Ви" }).click();
  await expect(
    page.getByRole("button", { name: "Отменить операцию" }),
  ).toBeVisible({ timeout: 15000 });
  const cancelStarted = Date.now();
  await page.getByRole("button", { name: "Отменить операцию" }).click();
  await expect(page.getByText(/Операция отменена/)).toBeVisible();
  const cancelMs = Date.now() - cancelStarted;
  view = (await (
    await page.request.get(finance, { headers })
  ).json()) as Schemas["FinancialView"];
  expect(view.operation?.state).toBe("cancelled");
  expect(view.result).toBeNull();
  expect(
    Object.values(view.document.entries).some(
      (e) => e.method === "qwen_exploratory",
    ),
  ).toBe(false);
  await page.screenshot({ path: `${directory}/cancelled.png`, fullPage: true });
  await page.getByRole("button", { name: "Предложить допущения с Ви" }).click();
  await expect(
    page.getByRole("button", { name: "Отменить операцию" }),
  ).toBeVisible({ timeout: 15000 });
  const interruptedStarted = Date.now();
  await page.reload();
  await expect
    .poll(
      async () => {
        view = (await (
          await page.request.get(finance, { headers })
        ).json()) as Schemas["FinancialView"];
        return view.operation?.state;
      },
      { timeout: 20000 },
    )
    .toBe("interrupted");
  const interruptedMs = Date.now() - interruptedStarted;
  await expect(page.getByText(/^Запрос прерван/)).toBeVisible({
    timeout: 10000,
  });
  expect(view.result).toBeNull();
  expect(proposalRequests).toBe(2);
  await page.screenshot({
    path: `${directory}/interrupted.png`,
    fullPage: true,
  });
  // Explicit manual recovery, not a fake successful model result.
  const manual = {
    students: "20",
    tuition: "6500",
    variable_per_student: "500",
    fee_ratio: "0.05",
  };
  view = (await (
    await page.request.patch(finance, {
      headers,
      data: {
        ...command(),
        updates: Object.entries(manual).map(([parameter, value]) => ({
          parameter,
          unit: view.configuration.parameters.find((p) => p.id === parameter)!
            .unit,
          base: value,
          low: value,
          high: value,
          kind: "user_assumption",
          basis:
            "Explicit manual recovery after cancelled/interrupted inference",
        })),
      },
    })
  ).json()) as Schemas["FinancialView"];
  view = (await (
    await page.request.post(finance + "/review", {
      headers,
      data: { ...command(), confirm: Object.keys(view.document.entries) },
    })
  ).json()) as Schemas["FinancialView"];
  view = (await (
    await page.request.post(finance + "/calculate", {
      headers,
      data: command(),
    })
  ).json()) as Schemas["FinancialView"];
  expect(view.result?.result.status).toBe("calculated");
  const snapshot = view.result!;
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Базовый", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Продолжить к возможностям банка" })
    .click();
  await page.getByRole("button", { name: "Продолжить без подбора" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Предварительный результат",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.locator(".summary-screen .vi-status")).toHaveAttribute(
    "data-emotion",
    "neutral",
  );
  await context.setOffline(true);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    page.getByRole("button", { name: "Повторить проверку" }),
  ).toBeVisible();
  expect(
    await page.getByRole("heading", { name: "Базовый", exact: true }).count(),
  ).toBe(0);
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(
    page.getByRole("heading", { name: "Базовый", exact: true }),
  ).toBeVisible();
  expect(
    (
      await (
        await page.request.get(base + "/analysis-result", { headers })
      ).json()
    ).financial,
  ).toEqual(snapshot);
  expect(proposalRequests).toBe(2);
  const changed = await page.request.patch(finance, {
    headers,
    data: {
      ...command(),
      updates: [
        {
          parameter: "marketing",
          unit: "RUB/month",
          base: "31000",
          low: "31000",
          high: "31000",
        },
      ],
    },
  });
  expect(changed.status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    page.getByRole("heading", { name: "Базовый", exact: true }),
  ).toHaveCount(0);
  const stale = await (
    await page.request.get(base + "/analysis-result", { headers })
  ).json();
  expect(stale.financial).toBeNull();
  expect(stale.state).toBe("partial");
  expect(
    await (
      await page.request.get(finance + "/results/" + snapshot.id, { headers })
    ).json(),
  ).toEqual(snapshot);
  await page.screenshot({ path: `${directory}/stale.png`, fullPage: true });
  expect(
    (
      await page.request.get(base + "/analysis-result", {
        headers: { "X-Conversation-Token": "x".repeat(64) },
      })
    ).status(),
  ).toBe(404);
  expect(
    (
      await page.request.put(legacy + "/consents/assistant", {
        headers,
        data: {
          expected_revision: 1,
          text_version: "assistant-demo-v1",
          decision: "withdraw",
        },
      })
    ).status(),
  ).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator(".summary-screen .vi-status")).toHaveAttribute(
    "data-emotion",
    "error",
  );
  expect(
    (await page.request.get(base + "/analysis-result", { headers })).status(),
  ).toBe(403);
  await page.screenshot({ path: `${directory}/revoked.png`, fullPage: true });
  expect(pageErrors).toEqual([]);
  expect(
    expectedConsoleErrors.every((e) =>
      /ERR_INTERNET_DISCONNECTED|403|499|ERR_ABORTED|Failed to fetch/.test(e),
    ),
  ).toBe(true);
  await writeFile(
    `${directory}/evidence.json`,
    JSON.stringify(
      {
        model: "qwen3:4b-instruct-2507-q4_K_M",
        cancelMs,
        interruptedMs,
        proposalRequests,
        cancellation: "cancelled",
        reloadDuringInference: "interrupted",
        noUnreviewedModelValues: true,
        manualRecovery: true,
        financialResultId: snapshot.id,
        offlineRecoverySameSnapshot: true,
        staleHidden: true,
        historicalSnapshotUnchanged: true,
        foreignOwnerStatus: 404,
        revokedStatus: 403,
        pageErrors,
        expectedConsoleErrors,
        note: "Controlled network/cancel/consent errors are expected; manual recovery is not model success",
      },
      null,
      2,
    ),
  );
});
