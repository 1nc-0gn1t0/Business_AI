import { test, expect } from "@playwright/test";
import { setupFlow, openChat, goFinance } from "./flow.mock";

for (const width of [1440, 768, 390])
  test(`Vi ${width}px: honest landing, lazy images, keyboard and real workspace entry`, async ({
    page,
  }) => {
    await setupFlow(page, false);
    const assets: string[] = [];
    const api: string[] = [];
    page.on("request", (r) => {
      if (r.resourceType() === "image" && r.url().includes(".webp"))
        assets.push(r.url());
      if (r.url().includes("/api/")) api.push(r.url());
    });
    await page.setViewportSize({ width, height: width === 390 ? 568 : 1000 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /Ваш бизнес/ }),
    ).toBeVisible();
    await expect(page.getByRole("button")).toHaveCount(2);
    await expect(page.locator(".vi-dock > *")).toHaveCount(3);
    await page.locator(".vi-floating .vi-avatar").waitFor({ state: "visible" });
    expect(assets.every((u) => u.includes("/motion/"))).toBe(true);
    expect(api).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    const dock = await page.locator(".vi-dock").boundingBox();
    expect(dock!.x + dock!.width).toBeLessThanOrEqual(width);
    expect(dock!.y + dock!.height).toBeLessThanOrEqual(
      width === 390 ? 568 : 1000,
    );
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "Перейти к содержимому" }),
    ).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("button", { name: "Познакомиться с Ви", exact: true }),
    ).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("button", { name: "Познакомьтесь с Ви" }),
    ).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    const panel = await page.getByRole("dialog").boundingBox();
    expect(panel!.x).toBeGreaterThanOrEqual(0);
    expect(panel!.x + panel!.width).toBeLessThanOrEqual(width);
    expect(panel!.y).toBeGreaterThanOrEqual(0);
    expect(panel!.y + panel!.height).toBeLessThanOrEqual(
      width === 390 ? 568 : 1000,
    );
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Познакомьтесь с Ви" }),
    ).toBeFocused();
    await page.getByRole("button", { name: "Познакомьтесь с Ви" }).click();
    await page.getByRole("button", { name: "Закрыть приветствие Ви" }).click();
    await page.getByRole("button", { name: "Познакомьтесь с Ви" }).click();
    await page.mouse.click(2, 2);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Познакомьтесь с Ви" }).click();
    await page.getByRole("button", { name: "Начать с Ви" }).click();
    await expect(
      page.getByRole("heading", { name: "Какой бизнес вы хотите открыть?" }),
    ).toBeVisible();
    await expect(page.locator(".vi-dock")).toHaveCount(0);
    await page.getByLabel("Сообщение помощнику").fill("Сохраняемый черновик");
    await page.getByRole("button", { name: "Business AI · главная" }).click();
    await page.getByRole("button", { name: "Познакомьтесь с Ви" }).click();
    await page.getByRole("button", { name: "Начать с Ви" }).click();
    await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
      "Сохраняемый черновик",
    );
    // Browser Back while consent is open must release native modal inertness.
    await page.getByLabel("Отправить сообщение").click();
    await expect(
      page.getByRole("dialog", { name: "Перед началом" }),
    ).toBeVisible();
    await page.goBack();
    await expect(
      page.getByRole("heading", { name: /Ваш бизнес/ }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Познакомьтесь с Ви" }).click();
    await page.getByRole("button", { name: "Начать с Ви" }).click();
    await expect(
      page.getByRole("dialog", { name: "Перед началом" }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Согласен на использование ассистента"),
    ).not.toBeChecked();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Назад", exact: true })
      .click();
    await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
      "Сохраняемый черновик",
    );
  });

test("Vi uses actual pending/error/stale states, not success timers", async ({
  page,
}) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await openChat(page);
  let release: () => void = () => {};
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/messages", async (r) => {
    await barrier;
    return r.fulfill({
      status: 503,
      json: { detail: { code: "llm_unavailable" } },
      headers: { "X-Request-ID": "a".repeat(32) },
    });
  });
  await page.getByLabel("Сообщение помощнику").fill("Проверка отказа");
  await page.getByLabel("Отправить сообщение").click();
  await expect(page.locator(".vi-chat")).toHaveAttribute(
    "data-emotion",
    "working",
  );
  await expect(page.getByText("Обдумываю…")).toBeVisible();
  release();
  await expect(page.getByRole("alert")).toContainText("a".repeat(32));
  await expect(page.getByRole("alert").locator("img")).toHaveAttribute(
    "src",
    /error/,
  );
  await expect(page.getByText("Обдумываю…")).toHaveCount(0);
  await expect(page.getByLabel("Сообщение помощнику")).toHaveValue(
    "Проверка отказа",
  );
});

test("Vi completion means calculation completed, including a negative scenario", async ({
  page,
}) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await goFinance(page);
  await expect(page.locator(".finance .vi-status")).toHaveAttribute(
    "data-emotion",
    "idea",
  );
  await expect(page.getByText("Отрицательный результат")).toBeVisible();
  await page.getByLabel("Аренда", { exact: true }).fill("100000");
  await expect(page.locator(".finance .vi-status")).toHaveAttribute(
    "data-emotion",
    "uncertain",
  );
  await expect(
    page.getByRole("button", { name: "Продолжить", exact: true }),
  ).toBeDisabled();
});
