import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const appUrl = process.env.FE04_APP_URL || "http://127.0.0.1:5173";
const apiUrl = process.env.FE04_API_URL || "http://127.0.0.1:5174";
const storageKey = "rag-workbench-conversations-v1";
const benchmarkDirectory = path.dirname(fileURLToPath(import.meta.url));
const artifactDirectory = path.resolve(
  benchmarkDirectory,
  "../../artifacts/frontend-3.1.0/fe04/real-zoom",
);
const evidencePath = path.join(artifactDirectory, "evidence.json");
const temporaryRoot = path.resolve(os.tmpdir());
const profileDirectory = await mkdtemp(
  path.join(temporaryRoot, "documind-fe04-zoom-"),
);

const conversationTitle =
  "FE-04 真实 200% 缩放下的超长中文会话标题-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789";
const documentName =
  "DocuMind-FE04-真实缩放超长中文文档名-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789.txt";
const wideTableCell = `WIDETABLE${"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".repeat(24)}`;
const longCodeLine = `const realZoomEvidence = "${"long-code-segment-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".repeat(20)}";`;

const conversation = [
  {
    id: "fe04-real-zoom-conversation",
    title: conversationTitle,
    updatedAt: "2026-09-21T01:00:00.000Z",
    messages: [
      {
        id: "fe04-real-zoom-question",
        role: "user",
        content: "请验证真实浏览器 200% 缩放下的长文本、宽表格和长代码。",
        stage: "done",
        sources: [],
      },
      {
        id: "fe04-real-zoom-answer",
        role: "assistant",
        content: [
          "这是一段用于验证真实浏览器缩放、中文换行和有效信息可读性的回答。",
          "",
          "| 检查项目 | 不可断开的宽内容 |",
          "| --- | --- |",
          `| 横向滚动 | ${wideTableCell} |`,
          "",
          "```ts",
          longCodeLine,
          "```",
        ].join("\n"),
        stage: "done",
        sources: [
          {
            rank: 1,
            source: "真实缩放来源文件名-不会挤压关闭入口-ABCDEFGHIJKLMNOPQRSTUVWXYZ.txt",
            excerpt: "第一条来源用于检查真实 200% 缩放下的抽屉、换行与局部滚动。",
            chunk_id: "fe04-real-zoom-source-1",
            page_number: 200,
            distance: 0.125,
            rerank_score: 0.9876,
          },
          {
            rank: 2,
            source: "第二条真实缩放来源文件名-ABCDEFGHIJKLMNOPQRSTUVWXYZ.txt",
            excerpt: "第二条来源用于确认紧凑视口中的多卡片布局与关闭按钮可达。",
            chunk_id: "fe04-real-zoom-source-2",
            page_number: 400,
            distance: 0.25,
            fusion_score: 0.76543,
          },
        ],
      },
    ],
  },
];

const documentRecord = {
  document_key: "fe04-real-zoom-document",
  display_name: documentName,
  status: "active",
  chunk_count: 128,
  file_type: ".txt",
  file_size_bytes: 1_234_567,
  active_index_id: "fe04-real-zoom-index",
  active_version_id: "fe04-real-zoom-version-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  version_count: 1,
  error_type: null,
  created_at: "2026-09-21T01:00:00.000Z",
  updated_at: "2026-09-21T01:00:00.000Z",
};

async function waitForDevToolsPort() {
  const activePortPath = path.join(profileDirectory, "DevToolsActivePort");
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const [port] = (await readFile(activePortPath, "utf8")).trim().split(/\r?\n/);
      if (port) return Number(port);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("Chromium did not expose DevToolsActivePort within 15 seconds.");
}

async function removeTemporaryProfile() {
  const resolvedProfile = path.resolve(profileDirectory);
  assert.ok(
    resolvedProfile.startsWith(`${temporaryRoot}${path.sep}`),
    "Refusing to remove a profile outside the temporary directory.",
  );
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      await rm(resolvedProfile, { recursive: true, force: true });
      return;
    } catch (error) {
      if (!["EBUSY", "EPERM", "ENOTEMPTY"].includes(error?.code) || attempt === 19) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
}

async function updateMockState(payload) {
  const response = await fetch(`${apiUrl}/__e2e/state`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  assert.equal(response.ok, true, `Mock state update failed: ${response.status}`);
}

async function measureLayout(page, state) {
  const result = await page.evaluate(() => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        rect.width > 0 &&
        rect.height > 0
      );
    };
    const viewportWidth = document.documentElement.clientWidth;
    const outside = Array.from(
      document.querySelectorAll(
        "button:not([hidden]), textarea:not([hidden]), [role='dialog'], .sources-panel, .message-body pre, .message-body table",
      ),
    )
      .filter(visible)
      .flatMap((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left < -1 || rect.right > viewportWidth + 1
          ? [
              {
                label: (
                  element.getAttribute("aria-label") ||
                  element.textContent ||
                  element.className
                )
                  .trim()
                  .replace(/\s+/g, " ")
                  .slice(0, 80),
                left: rect.left,
                right: rect.right,
              },
            ]
          : [];
      });

    return {
      documentOverflow:
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
      bodyOverflow: document.body.scrollWidth - document.documentElement.clientWidth,
      outside,
      activeElement:
        document.activeElement?.getAttribute("aria-label") ||
        document.activeElement?.textContent?.trim().replace(/\s+/g, " ").slice(0, 80) ||
        document.activeElement?.tagName,
    };
  });
  assert.ok(result.documentOverflow <= 1, `${state}: document overflowed`);
  assert.ok(result.bodyOverflow <= 1, `${state}: body overflowed`);
  assert.deepEqual(result.outside, [], `${state}: controls escaped the viewport`);
  return { state, ...result };
}

async function capture(page, filename, fullPage = false) {
  const outputPath = path.join(artifactDirectory, filename);
  const session = await page.context().newCDPSession(page);
  try {
    const layout = await session.send("Page.getLayoutMetrics");
    const devicePixelRatio = await page.evaluate(() => window.devicePixelRatio);
    const target = fullPage
      ? {
          x: 0,
          y: 0,
          width: layout.cssContentSize.width,
          height: layout.cssContentSize.height,
        }
      : {
          x: layout.cssVisualViewport.pageX,
          y: layout.cssVisualViewport.pageY,
          width: layout.cssVisualViewport.clientWidth,
          height: layout.cssVisualViewport.clientHeight,
        };
    const { data } = await session.send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: true,
      clip: {
        x: target.x * devicePixelRatio,
        y: target.y * devicePixelRatio,
        width: target.width * devicePixelRatio,
        height: target.height * devicePixelRatio,
        scale: 1,
      },
    });
    const image = Buffer.from(data, "base64");
    const width = image.readUInt32BE(16);
    const height = image.readUInt32BE(20);
    assert.ok(
      Math.abs(width - target.width * devicePixelRatio) <= 2,
      `${filename}: screenshot width was cropped (${width}px)`,
    );
    assert.ok(
      Math.abs(height - target.height * devicePixelRatio) <= 2,
      `${filename}: screenshot height was cropped (${height}px)`,
    );
    assert.ok(image.length >= 20_000, `${filename}: screenshot had too little pixel data`);
    await writeFile(outputPath, image);
    return { outputPath, width, height, bytes: image.length };
  } finally {
    await session.detach();
  }
}

await mkdir(artifactDirectory, { recursive: true });
await rm(evidencePath, { force: true });
process.env.NO_PROXY = "127.0.0.1,localhost";
process.env.no_proxy = "127.0.0.1,localhost";

const browserProcess = spawn(
  chromium.executablePath(),
  [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${profileDirectory}`,
    "--window-size=1440,900",
    "--no-first-run",
    "--no-default-browser-check",
  ],
  { stdio: "ignore", windowsHide: true },
);

let browser;
try {
  const port = await waitForDevToolsPort();
  browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  const context = browser.contexts()[0];
  assert.ok(context, "Chromium did not expose a default browser context.");

  const settingsPagePromise = context.waitForEvent("page");
  const settingsResponse = await fetch(
    `http://127.0.0.1:${port}/json/new?${encodeURIComponent("chrome://settings/appearance")}`,
    { method: "PUT" },
  );
  assert.equal(settingsResponse.ok, true, "Failed to open Chromium appearance settings.");
  const settingsPage = await settingsPagePromise;
  await settingsPage.waitForLoadState("domcontentloaded");
  const zoomSelect = settingsPage.locator("select#zoomLevel");
  await zoomSelect.selectOption("2");
  assert.equal(await zoomSelect.inputValue(), "2");

  const resetResponse = await fetch(`${apiUrl}/__e2e/reset`, { method: "POST" });
  assert.equal(resetResponse.ok, true, `Mock reset failed: ${resetResponse.status}`);
  await updateMockState({ documents: [documentRecord] });

  const page = await context.newPage();
  await page.addInitScript(
    ({ key, value }) => localStorage.setItem(key, value),
    { key: storageKey, value: JSON.stringify(conversation) },
  );
  await page.goto(appUrl);
  await page.getByText("服务就绪", { exact: true }).waitFor();
  await page.locator(".message").nth(1).waitFor();

  const metrics = await page.evaluate(() => ({
    devicePixelRatio: window.devicePixelRatio,
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    outerWidth: window.outerWidth,
    outerHeight: window.outerHeight,
    visualScale: window.visualViewport?.scale,
    compactSources: window.matchMedia("(max-width: 860px)").matches,
    htmlClientWidth: document.documentElement.clientWidth,
    htmlScrollWidth: document.documentElement.scrollWidth,
  }));
  assert.equal(metrics.devicePixelRatio, 2, "Browser did not apply 200% page zoom.");
  assert.equal(metrics.outerWidth, 1440, "Outer browser width changed unexpectedly.");
  assert.equal(metrics.outerHeight, 900, "Outer browser height changed unexpectedly.");
  assert.ok(metrics.innerWidth <= 720, "200% zoom did not halve the CSS viewport.");
  assert.equal(metrics.compactSources, true, "Compact breakpoint was not active.");

  const scrollRegions = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".message-body pre, .message-body table")).map(
      (element) => ({
        tag: element.tagName.toLowerCase(),
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        overflowX: getComputedStyle(element).overflowX,
      }),
    ),
  );
  assert.deepEqual(scrollRegions.map(({ tag }) => tag).sort(), ["pre", "table"]);
  for (const region of scrollRegions) {
    assert.ok(region.scrollWidth > region.clientWidth, `${region.tag} did not scroll locally`);
    assert.ok(["auto", "scroll"].includes(region.overflowX));
  }

  const states = [];
  const screenshots = [];
  states.push(await measureLayout(page, "workspace"));
  screenshots.push(await capture(page, "200-percent-workspace.png"));
  screenshots.push(await capture(page, "200-percent-workspace-full-page.png", true));

  const composer = page.getByPlaceholder("向知识库提问");
  await page.getByRole("button", { name: "新建对话" }).focus();
  for (let step = 0; step < 40; step += 1) {
    await page.keyboard.press("Tab");
    if (await composer.evaluate((element) => element === document.activeElement)) break;
  }
  assert.equal(await composer.evaluate((element) => element === document.activeElement), true);
  await composer.scrollIntoViewIfNeeded();
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => resolve())));
  screenshots.push(await capture(page, "200-percent-focus.png"));

  const sourceTrigger = page.getByRole("button", { name: "2 条引用来源" });
  await sourceTrigger.click();
  const sourcesDialog = page.getByRole("dialog", { name: "引用来源" });
  await sourcesDialog.waitFor();
  assert.equal(await sourcesDialog.getAttribute("aria-modal"), "true");
  assert.equal(
    await sourcesDialog
      .getByRole("button", { name: "关闭引用来源" })
      .evaluate((element) => element === document.activeElement),
    true,
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  states.push(await measureLayout(page, "sources"));
  screenshots.push(await capture(page, "200-percent-sources.png"));
  await page.keyboard.press("Escape");
  await sourcesDialog.waitFor({ state: "hidden" });
  assert.equal(await sourceTrigger.evaluate((element) => element === document.activeElement), true);

  const documentTrigger = page.getByRole("button", {
    name: `查看文档 ${documentName}`,
    exact: true,
  });
  await documentTrigger.click();
  const documentDialog = page.getByRole("dialog", { name: documentName });
  await documentDialog.waitFor();
  await page.evaluate(() => window.scrollTo(0, 0));
  states.push(await measureLayout(page, "document-dialog"));
  screenshots.push(await capture(page, "200-percent-document-dialog.png"));

  await documentDialog.getByRole("button", { name: "删除文档", exact: true }).click();
  const deleteDialog = page.getByRole("dialog", {
    name: "删除文档及全部向量索引？",
  });
  await deleteDialog.waitFor();
  await page.evaluate(() => window.scrollTo(0, 0));
  states.push(await measureLayout(page, "document-delete"));
  screenshots.push(await capture(page, "200-percent-document-delete.png"));
  await deleteDialog.getByRole("button", { name: "取消" }).click();
  await documentDialog.getByRole("button", { name: "关闭文档详情" }).click();

  await page.getByRole("button", { name: "清空当前对话" }).click();
  const conversationDialog = page.getByRole("dialog", { name: "清空当前对话？" });
  await conversationDialog.waitFor();
  await page.evaluate(() => window.scrollTo(0, 0));
  states.push(await measureLayout(page, "conversation-confirm"));
  screenshots.push(await capture(page, "200-percent-conversation-confirm.png"));
  await conversationDialog.getByRole("button", { name: "取消" }).click();

  const evidence = {
    status: "PASS",
    browserVersion: browser.version(),
    settingsZoomValue: await zoomSelect.inputValue(),
    metrics,
    scrollRegions,
    states,
    screenshotCapture: "CDP Page.captureScreenshot with a DPR-adjusted physical clip",
    screenshots: screenshots.map(({ outputPath, width, height, bytes }) => ({
      file: path.relative(artifactDirectory, outputPath),
      width,
      height,
      bytes,
    })),
  };
  await writeFile(evidencePath, `${JSON.stringify(evidence, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(evidence, null, 2));
} finally {
  try {
    const browserSession = await browser?.newBrowserCDPSession();
    await browserSession?.send("Browser.close");
  } catch {
    // Fall back to the exact process handle below if the CDP session is unavailable.
  }
  try {
    await browser?.close();
  } catch {
    // The browser may already be closing after a failed assertion.
  }
  if (!browserProcess.killed) browserProcess.kill();
  await removeTemporaryProfile();
}
