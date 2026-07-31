import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { PNG } from "pngjs";

const healthPayload = {
  status: "ok",
  service: "canvasrelay-api",
  version: "0.1.0",
  demoMode: true,
  timestamp: "2026-08-01T00:00:00Z",
};

async function mockApiOnline(page: Page) {
  await page.route("**/api/v1/health", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(healthPayload) });
  });
}

function collectConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

async function attachViewportScreenshot(page: Page, testInfo: TestInfo, name: string) {
  await testInfo.attach(name, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
}

const viewports = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "tablet", width: 820, height: 1180 },
  { name: "mobile", width: 390, height: 844 },
] as const;

for (const viewport of viewports) {
  test(`${viewport.name} shell stays framed without overflow or control overlap`, async ({ page }, testInfo) => {
    const consoleErrors = collectConsoleErrors(page);
    await page.setViewportSize(viewport);
    await mockApiOnline(page);
    await page.goto("/image");

    await expect(page.getByText("Connected", { exact: true })).toBeVisible();
    await expect(page.getByTestId("stage-2d")).toBeVisible();

    const layout = await page.evaluate(() => {
      const visibleControls = [...document.querySelectorAll<HTMLElement>("button, select, a")].filter((element) => {
        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();
        return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
      });
      const outsideControls = visibleControls
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          return rect.left < -1 || rect.right > window.innerWidth + 1;
        })
        .map((element) => element.getAttribute("aria-label") ?? element.textContent?.trim() ?? element.tagName);

      return {
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        outsideControls,
      };
    });

    expect(layout.documentWidth).toBeLessThanOrEqual(layout.viewportWidth);
    expect(layout.outsideControls).toEqual([]);

    const stageBox = await page.getByRole("region", { name: "2D job stage" }).boundingBox();
    const inspectorBox = await page.getByRole("complementary", { name: "Job and API inspector" }).boundingBox();
    expect(stageBox).not.toBeNull();
    expect(inspectorBox).not.toBeNull();
    if (stageBox && inspectorBox) {
      if (viewport.width > 900) expect(stageBox.x + stageBox.width).toBeLessThanOrEqual(inspectorBox.x + 1);
      else expect(stageBox.y + stageBox.height).toBeLessThanOrEqual(inspectorBox.y + 1);
    }

    await attachViewportScreenshot(page, testInfo, `${viewport.name}-2d-shell`);
    expect(consoleErrors).toEqual([]);
  });
}

test("3D stage renders visible pixels, stays framed, and preserves selection", async ({ page }, testInfo) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApiOnline(page);
  await page.goto("/image");

  await page.getByRole("button", { name: "3D" }).click();
  const canvas = page.locator("canvas");
  await expect(canvas).toBeVisible();
  await page.waitForTimeout(1_000);

  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  expect(box?.width ?? 0).toBeGreaterThan(700);
  expect(box?.height ?? 0).toBeGreaterThan(600);

  const png = PNG.sync.read(await canvas.screenshot());
  let luminanceSum = 0;
  let luminanceSquaredSum = 0;
  let nonDarkPixels = 0;
  let sampledPixels = 0;
  for (let index = 0; index < png.data.length; index += 4 * 19) {
    const red = png.data[index] ?? 0;
    const green = png.data[index + 1] ?? 0;
    const blue = png.data[index + 2] ?? 0;
    const luminance = red * 0.2126 + green * 0.7152 + blue * 0.0722;
    luminanceSum += luminance;
    luminanceSquaredSum += luminance * luminance;
    if (luminance > 24) nonDarkPixels += 1;
    sampledPixels += 1;
  }
  const mean = luminanceSum / sampledPixels;
  const variance = luminanceSquaredSum / sampledPixels - mean * mean;

  expect(variance).toBeGreaterThan(90);
  expect(nonDarkPixels / sampledPixels).toBeGreaterThan(0.04);

  await page.getByRole("button", { name: "Frame compose" }).last().click();
  await expect(page.getByRole("heading", { name: "Frame compose" })).toBeVisible();

  await page.getByRole("button", { name: "2D" }).click();
  await expect(page.getByTestId("stage-2d")).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(0);
  await page.getByRole("button", { name: "3D" }).click();
  await expect(page.locator("canvas")).toHaveCount(1);
  await attachViewportScreenshot(page, testInfo, "desktop-3d-stage");
  expect(consoleErrors).toEqual([]);
});

test("mock jobs transition and demo restart restores the initial state", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await mockApiOnline(page);
  await page.goto("/image");

  const previewJob = page.getByRole("button", { name: /Preview export/iu }).first();
  await expect(previewJob).toHaveAttribute("data-status", "queued");
  await expect(previewJob).toHaveAttribute("data-status", "running", { timeout: 5_000 });

  await page.getByRole("button", { name: "Demo restart" }).click();
  await expect(previewJob).toHaveAttribute("data-status", "queued");
  await expect(page.getByText("1 queued")).toBeVisible();
  await expect(page.getByText("1 running")).toBeVisible();
  await expect(page.getByText("1 complete")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("API failure is distinct and recovers through the inspector retry", async ({ page }) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.route("**/api/v1/health", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "{" }),
  );
  await page.goto("/image");

  await expect(page.getByText("API unavailable").first()).toBeVisible();
  await page.unroute("**/api/v1/health");
  await mockApiOnline(page);
  await page.getByRole("button", { name: "Check API connection again" }).click();
  await expect(page.getByText("API connected")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("reduced motion pauses the 3D scene loop", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockApiOnline(page);
  await page.goto("/image");
  await page.getByRole("button", { name: "3D" }).click();

  await expect(page.getByTestId("stage-3d")).toHaveAttribute("data-motion", "paused");
});
