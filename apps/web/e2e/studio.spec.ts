import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { PNG } from "pngjs";

const healthPayload = {
  status: "ok",
  service: "canvasrelay-api",
  version: "0.1.0",
  demoMode: true,
  timestamp: "2026-08-01T00:00:00Z",
};

const completedImageJob = {
  id: "img_e2e_complete",
  status: "completed",
  progress: 100,
  phase: "completed",
  currentStep: 8,
  totalSteps: 8,
  progressSource: "provider",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "A precise persistent studio image",
  settings: {
    aspectRatio: "4:3",
    style: "editorial",
    seed: 42,
    provider: "demo",
    operation: "edit",
    hasFaceReference: true,
    sourceJobId: null,
    edit: {
      steps: 8,
      cfg: 1,
      referenceInfluence: 4,
      groundingResolution: 768,
      fitMode: "fit",
      sampler: "euler",
      scheduler: "simple",
      loras: [],
    },
  },
  createdAt: "2026-08-01T00:00:00Z",
  startedAt: "2026-08-01T00:00:01Z",
  completedAt: "2026-08-01T00:00:04Z",
  result: {
    url: "/api/v1/image-jobs/img_e2e_complete/result",
    thumbnailUrl: "/api/v1/image-jobs/img_e2e_complete/thumbnail",
    mimeType: "image/svg+xml",
    width: 960,
    height: 720,
    sizeBytes: 4096,
    sha256: "a".repeat(64),
    available: true,
  },
  error: null,
};

const resultSvg = `
  <svg xmlns="http://www.w3.org/2000/svg" width="960" height="720">
    <rect width="960" height="720" fill="#111923"/>
    <rect x="80" y="70" width="800" height="580" fill="#dbe6f5"/>
    <path d="M80 520 L420 160 L720 650 L80 650 Z" fill="#4f83c2"/>
    <circle cx="690" cy="260" r="110" fill="#d4a84d"/>
  </svg>`;

async function mockApiOnline(page: Page) {
  await page.route("**/api/v1/health", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(healthPayload) });
  });
  await page.route("**/api/v1/providers/image", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        provider: "demo",
        mode: "demo",
        label: "Deterministic demo",
        ready: true,
        message: "Ready.",
      }),
    });
  });
  await page.route("**/api/v1/providers/image/options", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        samplers: ["euler"],
        schedulers: ["simple"],
        loras: [],
        defaults: {
          steps: 8,
          cfg: 1,
          shift: 3.1,
          sampler: "euler",
          scheduler: "simple",
        },
      }),
    });
  });
  await page.route("**/api/v1/image-jobs?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], nextCursor: null }),
    });
  });
}

async function mockPersistentImageApi(page: Page) {
  await mockApiOnline(page);
  await page.route("**/api/v1/providers/image-edit/options", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      samplers: ["euler"], schedulers: ["simple"], loras: [],
      defaults: { steps: 8, cfg: 1, sampler: "euler", scheduler: "simple" },
    }),
  }));
  await page.route("**/api/v1/providers/image-edit", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      provider: "demo", mode: "demo", label: "Deterministic demo", ready: true, message: "Ready.",
    }),
  }));
  await page.route("**/api/v1/image-jobs?*", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [completedImageJob], nextCursor: null }),
  }));
  await page.route("**/api/v1/image-jobs/tags", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ tags: [] }),
  }));
  await page.route("**/api/v1/image-jobs/img_e2e_complete", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(completedImageJob),
  }));
  await page.route("**/api/v1/image-jobs/img_e2e_complete/result", (route) => route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: resultSvg,
  }));
  await page.route("**/api/v1/image-jobs/img_e2e_complete/thumbnail", (route) => route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: resultSvg,
  }));
  await page.route("**/api/v1/image-jobs/img_e2e_complete/inputs/*", (route) => route.fulfill({
    status: 200,
    contentType: "image/svg+xml",
    body: resultSvg,
  }));
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
    const inspectorBox = await page.getByRole("region", { name: "Selected job inspector" }).boundingBox();
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
  await mockApiOnline(page);
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

test("Job Center restores a durable selection and stays inside the viewport", async ({ page }, testInfo) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockPersistentImageApi(page);
  await page.goto("/jobs?job=img_e2e_complete");

  await expect(page.getByRole("heading", { name: "Job center" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Selected job details" })).toContainText(
    "A precise persistent studio image",
  );
  await expect(page.getByText("100%").last()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await attachViewportScreenshot(page, testInfo, "desktop-job-center");
  expect(consoleErrors).toEqual([]);
});

test("Library shows provenance and hands the selected result to Edit", async ({ page }, testInfo) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.setViewportSize({ width: 820, height: 1180 });
  await mockPersistentImageApi(page);
  await page.goto("/library?job=img_e2e_complete");

  await expect(page.getByRole("heading", { name: "Image library" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Selected image details" })).toContainText(
    "euler / simple",
  );
  await expect(page.getByRole("link", { name: "Edit again" })).toHaveAttribute(
    "href",
    "/edit?sourceJobId=img_e2e_complete&restoreJobId=img_e2e_complete",
  );
  await attachViewportScreenshot(page, testInfo, "tablet-library-detail");
  expect(consoleErrors).toEqual([]);
});

test("Edit keeps references in the Inspector until Compare is requested", async ({ page }, testInfo) => {
  const consoleErrors = collectConsoleErrors(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await mockPersistentImageApi(page);
  await page.goto("/edit?sourceJobId=img_e2e_complete&restoreJobId=img_e2e_complete");

  const stage = page.getByRole("main", { name: "Image edit result stage" });
  await expect(stage.getByRole("img", { name: /Edited result/ })).toBeVisible();
  await expect(stage.getByRole("img", { name: "Edit source comparison" })).toHaveCount(0);
  await expect(page.getByRole("img", { name: "Source image preview" })).toBeVisible();
  await page.getByRole("button", { name: "Compare source and result" }).click();
  await expect(stage.getByRole("img", { name: "Edit source comparison" })).toBeVisible();
  await expect(page.getByRole("slider", { name: "Comparison position" })).toBeVisible();
  await attachViewportScreenshot(page, testInfo, "mobile-edit-result-stage");
  expect(consoleErrors).toEqual([]);
});
