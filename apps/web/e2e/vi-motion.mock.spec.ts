import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { env } from "node:process";
import { setupFlow, openChat, goBank } from "./flow.mock";

const videoDir = env.BA_VI_VIDEO_DIR;
test.use({
  viewport: { width: 1280, height: 900 },
  video: videoDir ? { mode: "on", size: { width: 1280, height: 900 } } : "off",
});
test.afterEach(async ({ page, context }, info) => {
  if (!videoDir) return;
  await mkdir(videoDir, { recursive: true });
  const video = page.video();
  await context.close();
  await video?.saveAs(`${videoDir}/${info.title.split(":")[0]}.webm`);
});

test("MOTION01: independent greeting, feathers, blink and return to rest", async ({
  page,
}) => {
  await setupFlow(page, false);
  await page.goto("/");
  await page
    .getByRole("button", { name: "Познакомиться с Ви", exact: true })
    .click();
  const rig = page.locator(".vi-welcome .vi-rig");
  await expect(rig).toBeVisible();
  // First record the actual uninterrupted1.8s gesture, then inspect its timeline.
  await rig
    .locator(".vi-rig-hand")
    .evaluate((el) => Promise.all(el.getAnimations().map((a) => a.finished)));
  await page.getByRole("button", { name: "Закрыть приветствие Ви" }).click();
  await page
    .getByRole("button", { name: "Познакомиться с Ви", exact: true })
    .click();
  async function sample(time: number) {
    return rig.evaluate((el, time) => {
      for (const animation of el.getAnimations({ subtree: true })) {
        animation.pause();
        animation.currentTime = time;
      }
      const style = (name: string) => getComputedStyle(el.querySelector(name)!);
      return {
        hand: style(".vi-rig-hand").rotate,
        body: style(".vi-rig-character").rotate,
        feather: style(".vi-rig-plume1").rotate,
        eye: style(".vi-rig-eye_left").scale,
      };
    }, time);
  }
  const blink = await sample(306);
  expect(blink.eye).not.toBe("1");
  const wave = await sample(450);
  expect(wave.hand).not.toBe(wave.body);
  expect(wave.hand).not.toBe("none");
  expect(wave.feather).not.toBe("none");
  const rest = await sample(2500);
  expect(["none", "0deg"]).toContain(rest.hand);
  expect(["none", "0deg"]).toContain(rest.feather);
});

test("MOTION02: reduced motion is static and keyboard entry remains usable", async ({
  page,
}) => {
  await setupFlow(page, false);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page
    .getByRole("button", { name: "Познакомьтесь с Ви", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(
    await page
      .locator(".vi-welcome .vi-rig")
      .evaluate((el) => el.getAnimations({ subtree: true }).length),
  ).toBe(0);
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Познакомьтесь с Ви", exact: true }),
  ).toBeFocused();
});

test("MOTION03: controlled-mock thinking stops moving while a slow request stays pending", async ({
  page,
}) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await openChat(page);
  let release = () => {};
  const barrier = new Promise<void>((r) => {
    release = r;
  });
  await page.route("**/messages", async (r) => {
    await barrier;
    await r.fulfill({
      status: 503,
      json: { detail: { code: "llm_unavailable" } },
    });
  });
  await page
    .getByLabel("Сообщение помощнику")
    .fill("Проверка анимации ожидания");
  await page.getByLabel("Отправить сообщение").click();
  const image = page.locator(".vi-chat .vi-motion-thinking");
  await expect(image).toBeVisible();
  await image.evaluate((el) =>
    Promise.all(el.getAnimations().map((a) => a.finished)),
  );
  expect(await image.evaluate((el) => el.getAnimations().length)).toBe(0);
  await expect(page.getByText("Обдумываю…")).toBeVisible();
  release();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText("Обдумываю…")).toHaveCount(0);
});

test("MOTION04: controlled-mock searching follows only an active geographic request", async ({
  page,
}) => {
  await setupFlow(page);
  let release = () => {};
  const barrier = new Promise<void>((r) => {
    release = r;
  });
  await page.route("**/rankings", async (r) => {
    await barrier;
    await r.fallback();
  });
  await page.goto("/#business-ai");
  await page
    .getByRole("button", { name: "Найти локации", exact: true })
    .click();
  const image = page.locator(".locations .vi-motion-searching");
  await expect(image).toBeVisible();
  await image.evaluate((el) =>
    Promise.all(el.getAnimations().map((a) => a.finished)),
  );
  release();
  await expect(page.locator(".zone-card")).toHaveCount(5);
  await expect(image).toHaveCount(0);
});

test("MOTION05: controlled-mock report success follows preparation and has a finite reaction", async ({
  page,
}) => {
  await setupFlow(page);
  await page.goto("/#business-ai");
  await goBank(page);
  await page
    .getByRole("button", { name: "Продолжить без подбора", exact: true })
    .click();
  await expect(page.locator(".report-export .vi-motion-success")).toHaveCount(
    0,
  );
  const file = page.waitForEvent("download");
  await page.getByRole("button", { name: "Скачать PDF", exact: true }).click();
  await file;
  const image = page.locator(".report-export .vi-motion-success");
  await expect(image).toBeVisible();
  await image.evaluate((el) =>
    Promise.all(el.getAnimations().map((a) => a.finished)),
  );
  await expect(
    page.getByText("Готово! Ваш предварительный план подготовлен."),
  ).toBeVisible();
});
