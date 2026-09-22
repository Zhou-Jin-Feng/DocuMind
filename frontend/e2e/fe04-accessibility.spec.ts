import {
  expect,
  test,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";

const apiUrl = "http://127.0.0.1:4174";
const storageKey = "rag-workbench-conversations-v1";

function seededConversation() {
  return [
    {
      id: "fe04-conversation",
      title: "FE-04 可访问性检查",
      updatedAt: "2026-09-21T01:00:00.000Z",
      messages: [
        {
          id: "fe04-question",
          role: "user",
          content: "什么是可访问的知识库界面？",
          stage: "done",
          sources: [],
        },
        {
          id: "fe04-answer",
          role: "assistant",
          content: [
            "界面需要清晰的焦点、语义和来源。",
            "",
            "| 检查项目 | 验收说明 |",
            "| --- | --- |",
            `| 键盘与重排 | ${"TABLESCROLLEVIDENCE0123456789".repeat(12)} |`,
            "",
            "```ts",
            `const accessibilityEvidence = \"${"long-code-segment-".repeat(18)}\";`,
            "```",
          ].join("\n"),
          stage: "done",
          sources: [
            {
              rank: 1,
              source: "超长来源文件名用于检查窄屏与焦点恢复.txt",
              excerpt: "键盘用户应能进入、离开并理解当前模态上下文。",
              chunk_id: "fe04-source",
              page_number: 4,
              distance: 0.1234,
            },
          ],
        },
      ],
    },
  ];
}

async function updateState(
  request: APIRequestContext,
  state: Record<string, unknown>,
): Promise<void> {
  const response = await request.post(`${apiUrl}/__e2e/state`, { data: state });
  expect(response.ok()).toBeTruthy();
}

async function loadSeededConversation(page: Page): Promise<void> {
  await page.addInitScript(
    ({ key, value }) => localStorage.setItem(key, value),
    { key: storageKey, value: JSON.stringify(seededConversation()) },
  );
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  await expect(page.locator(".message")).toHaveCount(2);
}

async function focusByKeyboard(
  page: Page,
  start: Locator,
  target: Locator,
  maxSteps = 50,
): Promise<void> {
  await start.focus();
  for (let step = 0; step < maxSteps; step += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => element === document.activeElement)) {
      return;
    }
  }
  throw new Error(`Keyboard focus did not reach the target within ${maxSteps} Tab presses.`);
}

async function uploadDocument(page: Page): Promise<Locator> {
  await page.locator('input[type="file"]').setInputFiles({
    name: "fe04-accessibility-guide.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("FE-04 文档弹窗与删除确认测试。", "utf-8"),
  });
  const trigger = page.getByRole("button", {
    name: "查看文档 fe04-accessibility-guide.txt",
  });
  await expect(trigger).toBeVisible();
  return trigger;
}

async function inspectVisibleContrast(page: Page) {
  return page.locator("body").evaluate(() => {
    type Rgba = [number, number, number, number];
    const parseColor = (value: string): Rgba | null => {
      const match = value.match(
        /rgba?\((\d+(?:\.\d+)?)[, ]+(\d+(?:\.\d+)?)[, ]+(\d+(?:\.\d+)?)(?:\s*[,/]\s*(\d+(?:\.\d+)?))?\)/,
      );
      if (!match) return null;
      return [
        Number(match[1]),
        Number(match[2]),
        Number(match[3]),
        match[4] === undefined ? 1 : Number(match[4]),
      ];
    };
    const luminance = ([red, green, blue]: Rgba) => {
      const channels = [red, green, blue].map((channel) => {
        const normalized = channel / 255;
        return normalized <= 0.03928
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    };
    const contrast = (foreground: Rgba, background: Rgba) => {
      const foregroundLuminance = luminance(foreground);
      const backgroundLuminance = luminance(background);
      return (
        (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
        (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
      );
    };
    const backgroundFor = (element: HTMLElement): Rgba => {
      let current: HTMLElement | null = element;
      while (current) {
        const color = parseColor(getComputedStyle(current).backgroundColor);
        if (color && color[3] === 1) return color;
        current = current.parentElement;
      }
      return [255, 255, 255, 1];
    };

    const failures = Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => {
        if (element.closest(".visually-hidden, [hidden], [aria-hidden='true'], :disabled")) {
          return false;
        }
        if (!element.textContent?.trim()) return false;
        if (Array.from(element.children).some((child) => child.textContent?.trim())) {
          return false;
        }
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return (
          rect.width > 0 &&
          rect.height > 0 &&
          style.display !== "none" &&
          style.visibility !== "hidden"
        );
      })
      .flatMap((element) => {
        const foreground = parseColor(getComputedStyle(element).color);
        if (!foreground || foreground[3] !== 1) return [];
        const ratio = contrast(foreground, backgroundFor(element));
        return ratio < 4.5
          ? [
              {
                element: `${element.tagName.toLowerCase()}.${Array.from(element.classList).join(".")}`,
                text: element.textContent?.trim().slice(0, 50),
                ratio: Number(ratio.toFixed(2)),
              },
            ]
          : [];
      });

    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const activeStyle = active ? getComputedStyle(active) : null;
    const focusColors = activeStyle
      ? [parseColor(activeStyle.boxShadow), parseColor(activeStyle.outlineColor)].filter(
          (color): color is Rgba => color !== null,
        )
      : [];
    return {
      failures,
      activeElement: active
        ? `${active.tagName.toLowerCase()}.${Array.from(active.classList).join(".")}`
        : null,
      focusContrast:
        active && focusColors.length
          ? Math.max(...focusColors.map((color) => contrast(color, backgroundFor(active))))
          : 0,
      focusShadow: activeStyle?.boxShadow ?? "none",
    };
  });
}

async function expectVisibleContrast(page: Page, state: string): Promise<void> {
  const result = await inspectVisibleContrast(page);
  expect(result.failures, `${state}: text contrast`).toEqual([]);
  expect(result.focusShadow, `${state}: ${result.activeElement} focus shadow`).not.toBe(
    "none",
  );
  expect(result.focusContrast, `${state}: ${result.activeElement} focus contrast`).toBeGreaterThanOrEqual(
    3,
  );
}

test.beforeEach(async ({ request }) => {
  const response = await request.post(`${apiUrl}/__e2e/reset`);
  expect(response.ok()).toBeTruthy();
});

test("会话确认使用安全初始焦点、循环焦点并恢复触发点", async ({ page }) => {
  await loadSeededConversation(page);
  const trigger = page.getByRole("button", { name: "清空当前对话" });
  await trigger.click();

  const dialog = page.getByRole("dialog", { name: "清空当前对话？" });
  const cancel = dialog.getByRole("button", { name: "取消" });
  const confirm = dialog.getByRole("button", { name: "清空对话", exact: true });
  await expect(dialog).toBeVisible();
  await expect(cancel).toBeFocused();

  await page.keyboard.press("Shift+Tab");
  await expect(confirm).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(cancel).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  await trigger.click();
  await expect(dialog).toBeVisible();
  await page.locator(".modal-overlay").last().click({ position: { x: 4, y: 4 } });
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("离线清空当前对话后焦点回退到新建对话", async ({ page }) => {
  await loadSeededConversation(page);
  await page.route(`${apiUrl}/api/v1/**`, (route) => route.abort("connectionrefused"));
  await page.reload();
  await expect(
    page.getByRole("alert").filter({ hasText: "问答服务未就绪" }),
  ).toBeVisible();
  await expect(page.locator(".message")).toHaveCount(2);
  await expect(page.getByPlaceholder("向知识库提问")).toBeDisabled();

  await page.getByRole("button", { name: "清空当前对话" }).click();
  const dialog = page.getByRole("dialog", { name: "清空当前对话？" });
  await expect(dialog.getByRole("button", { name: "取消" })).toBeFocused();
  await dialog.getByRole("button", { name: "清空对话", exact: true }).click();

  await expect(dialog).toBeHidden();
  await expect(page.locator(".message")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "新建对话" })).toBeFocused();
  await expect
    .poll(() => page.evaluate(() => document.activeElement === document.body))
    .toBe(false);
});

test("删除对话后触发点消失时焦点回退到新建对话", async ({ page }) => {
  await loadSeededConversation(page);
  await page
    .getByRole("button", { name: "删除对话 FE-04 可访问性检查" })
    .click();

  const dialog = page.getByRole("dialog", { name: "删除这条对话？" });
  await expect(dialog.getByRole("button", { name: "取消" })).toBeFocused();
  await dialog.getByRole("button", { name: "删除对话", exact: true }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByText("暂无历史对话", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "新建对话" })).toBeFocused();
});

test("文档详情圈定焦点，嵌套删除确认只关闭自身", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  const documentTrigger = await uploadDocument(page);
  await documentTrigger.click();

  const detailDialog = page.getByRole("dialog", {
    name: "fe04-accessibility-guide.txt",
  });
  const close = detailDialog.getByRole("button", { name: "关闭文档详情" });
  await expect(detailDialog).toBeVisible();
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(detailDialog.getByRole("button", { name: "删除文档" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(detailDialog).toBeHidden();
  await expect(documentTrigger).toBeFocused();

  await documentTrigger.click();
  const deleteTrigger = detailDialog.getByRole("button", { name: "删除文档" });
  await deleteTrigger.click();
  const deleteDialog = page.getByRole("dialog", {
    name: "删除文档及全部向量索引？",
  });
  await expect(page.locator('[role="dialog"]')).toHaveCount(2);
  await expect(deleteDialog.getByRole("button", { name: "取消" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(deleteDialog.getByRole("button", { name: "确认删除" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(deleteDialog.getByRole("button", { name: "取消" })).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(deleteDialog).toBeHidden();
  await expect(detailDialog).toBeVisible();
  await expect(deleteTrigger).toBeFocused();

  await deleteTrigger.click();
  await expect(deleteDialog.getByRole("button", { name: "取消" })).toBeFocused();
  await page.locator(".modal-overlay").last().click({ position: { x: 4, y: 4 } });
  await expect(deleteDialog).toBeHidden();
  await expect(detailDialog).toBeVisible();
  await expect(deleteTrigger).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(detailDialog).toBeHidden();
  await expect(documentTrigger).toBeFocused();
});

test("删除失败关闭内层确认并在外层播报错误", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  const documentTrigger = await uploadDocument(page);
  await documentTrigger.click();

  const detailDialog = page.getByRole("dialog", {
    name: "fe04-accessibility-guide.txt",
  });
  const deleteTrigger = detailDialog.getByRole("button", { name: "删除文档" });
  await expect(detailDialog).toBeVisible();
  await updateState(request, { online: false });

  try {
    await deleteTrigger.click();
    const deleteDialog = page.getByRole("dialog", {
      name: "删除文档及全部向量索引？",
    });
    await deleteDialog.getByRole("button", { name: "确认删除" }).click();

    await expect(deleteDialog).toBeHidden();
    await expect(page.locator('[role="dialog"]')).toHaveCount(1);
    await expect(detailDialog).toBeVisible();
    const errorNotice = detailDialog
      .getByRole("alert")
      .filter({ hasText: "测试后端暂不可用" });
    await expect(errorNotice).toBeVisible();
    await expect(errorNotice).toHaveAttribute("aria-live", "assertive");
    await expect(errorNotice).toHaveAttribute("aria-atomic", "true");
    await expect(deleteTrigger).toBeFocused();

    await updateState(request, { online: true });
    await deleteTrigger.click();
    await expect(deleteDialog).toBeVisible();
    const cancelRetry = deleteDialog.getByRole("button", { name: "取消" });
    await expect(cancelRetry).toBeFocused();
    await cancelRetry.click();
    await expect(deleteDialog).toBeHidden();
    await expect(detailDialog).toBeVisible();
  } finally {
    await updateState(request, { online: true });
  }
});

test("删除请求进行中不可关闭，成功后焦点回退到文档列表", async ({
  page,
  request,
}) => {
  await updateState(request, { holdDeleteResponse: true });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  const documentTrigger = await uploadDocument(page);
  await documentTrigger.click();
  const detailDialog = page.getByRole("dialog", {
    name: "fe04-accessibility-guide.txt",
  });
  await detailDialog.getByRole("button", { name: "删除文档" }).click();
  const deleteDialog = page.getByRole("dialog", {
    name: "删除文档及全部向量索引？",
  });
  await deleteDialog.getByRole("button", { name: "确认删除" }).click();

  await expect
    .poll(async () => {
      const response = await request.get(`${apiUrl}/__e2e/state`);
      const state = (await response.json()) as {
        deletePending: boolean;
        deleteRequestCount: number;
      };
      return {
        deletePending: state.deletePending,
        deleteRequestCount: state.deleteRequestCount,
      };
    })
    .toEqual({ deletePending: true, deleteRequestCount: 1 });
  const pendingStatus = deleteDialog.getByRole("status", { name: "正在删除" });
  await expect(pendingStatus).toBeFocused();
  await expect(pendingStatus).toHaveAttribute("aria-busy", "true");
  await page.keyboard.press("Tab");
  await expect(pendingStatus).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(pendingStatus).toBeFocused();
  await expect(deleteDialog.getByRole("button", { name: "正在删除" })).toBeDisabled();
  await expect(deleteDialog.getByRole("button", { name: "取消" })).toBeDisabled();
  const outerDialog = page.locator(".document-dialog");
  await expect(outerDialog.locator('button[aria-label="关闭文档详情"]')).toBeDisabled();
  await expect(outerDialog.locator("button").filter({ hasText: "重新建立索引" })).toBeDisabled();
  await expect(outerDialog.locator("button").filter({ hasText: "删除文档" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(deleteDialog).toBeVisible();
  await expect(page.locator('[role="dialog"]')).toHaveCount(2);
  await page.locator(".modal-overlay").last().click({
    position: { x: 4, y: 4 },
  });
  await expect(deleteDialog).toBeVisible();
  expect(
    await page.evaluate(() =>
      Boolean(
        document.querySelector<HTMLButtonElement>(
          '.modal-content button[aria-label="关闭文档详情"]',
        )?.disabled,
      ),
    ),
  ).toBe(true);
  await expect
    .poll(async () => {
      const response = await request.get(`${apiUrl}/__e2e/state`);
      const state = (await response.json()) as { deleteRequestCount: number };
      return state.deleteRequestCount;
    })
    .toBe(1);

  const release = await request.post(`${apiUrl}/__e2e/release-delete`);
  expect(release.ok()).toBeTruthy();

  await expect(page.locator('[role="dialog"]')).toHaveCount(0);
  await expect(page.getByText("知识库为空", { exact: true })).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => document.activeElement === document.querySelector(".document-list"),
      ),
    )
    .toBe(true);
});

test("窄屏来源是模态抽屉并在关闭后恢复回答触发点", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loadSeededConversation(page);
  const trigger = page.getByRole("button", { name: "1 条引用来源" });
  await trigger.click();

  const dialog = page.getByRole("dialog", { name: "引用来源" });
  const close = dialog.getByRole("button", { name: "关闭引用来源" });
  await expect(dialog).toBeVisible();
  const ariaModal = await dialog.getAttribute("aria-modal");
  await expect(close).toBeFocused();
  await expect(page.getByRole("button", { name: "新建对话" })).toHaveCount(0);
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(close).toBeFocused();

  await page.locator(".modal-overlay").last().click({ position: { x: 4, y: 4 } });
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();

  await trigger.click();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
  expect(ariaModal).toBe("true");
});

test("桌面来源保持非模态并允许继续操作背景", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await loadSeededConversation(page);

  await expect(page.getByRole("dialog", { name: "引用来源" })).toHaveCount(0);
  await expect(page.getByRole("complementary", { name: "引用来源" })).toBeVisible();
  const newConversation = page.getByRole("button", { name: "新建对话" });
  await expect(newConversation).toBeVisible();
  await newConversation.click();
  await expect(page.getByText("暂无对话", { exact: true })).toBeVisible();
});

test("来源区域在 861 到 860 动态断点安全切换为模态", async ({ page }) => {
  await page.setViewportSize({ width: 861, height: 900 });
  await loadSeededConversation(page);

  const desktopPanel = page.getByRole("complementary", { name: "引用来源" });
  const desktopClose = desktopPanel.getByRole("button", { name: "关闭引用来源" });
  await expect(desktopPanel).toBeVisible();
  await desktopClose.focus();
  await expect(desktopClose).toBeFocused();

  await page.setViewportSize({ width: 860, height: 900 });
  await expect(desktopPanel).toBeHidden();
  await expect(page.getByRole("dialog", { name: "引用来源" })).toHaveCount(0);
  const trigger = page.getByRole("button", { name: "展开引用来源" });
  await expect(trigger).toBeVisible();
  const focusRestoredAfterBreakpoint = await trigger.evaluate(
    (element) => element === document.activeElement,
  );

  await trigger.press("Enter");
  const dialog = page.getByRole("dialog", { name: "引用来源" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "关闭引用来源" })).toBeFocused();
  expect(focusRestoredAfterBreakpoint).toBe(true);
});

test("操作提示具有一致的 live-region 语义", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "notice.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("notice semantics", "utf-8"),
  });
  const successNotice = page.getByRole("status").filter({
    hasText: "索引完成，共生成 3 个片段。",
  });
  await expect(successNotice).toBeVisible();
  const dismissNotice = successNotice.getByRole("button", { name: "关闭提示" });
  await dismissNotice.focus();
  await expect(dismissNotice).toBeFocused();
  await dismissNotice.click();
  await expect(successNotice).toBeHidden();
  await expect(
    page.getByRole("button", { name: "上传文档", exact: true }),
  ).toBeFocused();

  await page.route(`${apiUrl}/api/v1/**`, (route) => route.abort("connectionrefused"));
  await page.reload();
  await expect(
    page.getByRole("alert").filter({ hasText: "问答服务未就绪" }),
  ).toBeVisible();
});

test("历史索引失败保持可见但不作为新状态重复播报", async ({ page, request }) => {
  await updateState(request, {
    documents: [
      {
        document_key: "failed-document",
        display_name: "failed-document.txt",
        status: "failed",
        chunk_count: 0,
        file_type: ".txt",
        file_size_bytes: 42,
        active_index_id: "failed-index",
        active_version_id: "failed-version",
        version_count: 1,
        error_type: "embedding_failed",
        created_at: "2026-09-21T01:00:00.000Z",
        updated_at: "2026-09-21T01:00:00.000Z",
      },
    ],
  });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "查看文档 failed-document.txt" })
    .click();

  const detailDialog = page.getByRole("dialog", { name: "failed-document.txt" });
  const notice = detailDialog
    .locator(".notice-inline")
    .filter({ hasText: "最近一次索引失败" });
  await expect(notice).toBeVisible();
  await expect(notice).toContainText("embedding_failed");
  await expect(
    page.getByRole("alert").filter({ hasText: "最近一次索引失败" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("status").filter({ hasText: "最近一次索引失败" }),
  ).toHaveCount(0);
  await expect(notice).not.toHaveAttribute("aria-live");
  await expect(notice).not.toHaveAttribute("aria-atomic");
});

test("输入焦点清晰且有效信息字号不低于 11px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await loadSeededConversation(page);
  const composer = page.getByPlaceholder("向知识库提问");
  await focusByKeyboard(
    page,
    page.getByRole("button", { name: "新建对话" }),
    composer,
  );
  await expect(composer).toBeFocused();
  expect(
    await composer.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth,
        outlineColor: style.outlineColor,
        boxShadow: style.boxShadow,
      };
    }),
  ).toMatchObject({
    outlineStyle: "solid",
    outlineWidth: "2px",
  });

  const undersized = await page.locator("body").evaluate(() => {
    const ignored = new Set(["SCRIPT", "STYLE"]);
    return Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => {
        if (ignored.has(element.tagName)) return false;
        if (element.classList.contains("visually-hidden")) return false;
        if (!element.textContent?.trim()) return false;
        if (Array.from(element.children).some((child) => child.textContent?.trim())) {
          return false;
        }
        const style = getComputedStyle(element);
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          Number.parseFloat(style.fontSize) < 11
        );
      })
      .map((element) => ({
        selector: `${element.tagName.toLowerCase()}.${Array.from(element.classList).join(".")}`,
        text: element.textContent?.trim().slice(0, 40),
        fontSize: getComputedStyle(element).fontSize,
      }));
  });
  expect(undersized).toEqual([]);

  const scrollable = await page.locator(".message-body pre, .message-body table").evaluateAll(
    (elements) =>
      elements.map((element) => ({
        tag: element.tagName.toLowerCase(),
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
      })),
  );
  expect(scrollable).toHaveLength(2);
  for (const region of scrollable) {
    expect(region.scrollWidth, `${region.tag} should have horizontal overflow`).toBeGreaterThan(
      region.clientWidth,
    );
  }

  const keyboardFocus = new Map<
    string,
    { outlineStyle: string; outlineWidth: string; boxShadow: string }
  >();
  await page.getByRole("button", { name: "新建对话" }).focus();
  for (let step = 0; step < 50; step += 1) {
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => {
      const active = document.activeElement as HTMLElement | null;
      if (!active) return null;
      const key = active.matches(".message-list")
        ? "message-list"
        : active.matches(".message-body pre")
          ? "pre"
          : active.matches(".message-body table")
            ? "table"
            : active.matches(".composer textarea")
              ? "composer"
              : null;
      if (!key) return null;
      const style = getComputedStyle(active);
      return {
        key,
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth,
        boxShadow: style.boxShadow,
      };
    });
    if (focused) keyboardFocus.set(focused.key, focused);
    if (keyboardFocus.size === 4) break;
  }
  expect(Object.fromEntries(keyboardFocus)).toMatchObject({
    "message-list": { outlineStyle: "solid", outlineWidth: "2px" },
    pre: { outlineStyle: "solid", outlineWidth: "2px" },
    table: { outlineStyle: "solid", outlineWidth: "2px" },
    composer: { outlineStyle: "solid", outlineWidth: "2px" },
  });
});

test("可见有效文字和焦点指示达到对比度门槛", async ({ page }) => {
  await loadSeededConversation(page);
  const composer = page.getByPlaceholder("向知识库提问");
  await focusByKeyboard(
    page,
    page.getByRole("button", { name: "新建对话" }),
    composer,
  );
  await expect(composer).toBeFocused();
  const result = await page.locator("body").evaluate(() => {
    type Rgba = [number, number, number, number];
    const parseColor = (value: string): Rgba | null => {
      const match = value.match(/rgba?\((\d+(?:\.\d+)?)[, ]+(\d+(?:\.\d+)?)[, ]+(\d+(?:\.\d+)?)(?:\s*[,/]\s*(\d+(?:\.\d+)?))?\)/);
      if (!match) return null;
      return [
        Number(match[1]),
        Number(match[2]),
        Number(match[3]),
        match[4] === undefined ? 1 : Number(match[4]),
      ];
    };
    const luminance = ([red, green, blue]: Rgba) => {
      const channels = [red, green, blue].map((channel) => {
        const normalized = channel / 255;
        return normalized <= 0.03928
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    };
    const contrast = (foreground: Rgba, background: Rgba) => {
      const foregroundLuminance = luminance(foreground);
      const backgroundLuminance = luminance(background);
      return (
        (Math.max(foregroundLuminance, backgroundLuminance) + 0.05) /
        (Math.min(foregroundLuminance, backgroundLuminance) + 0.05)
      );
    };
    const backgroundFor = (element: HTMLElement): Rgba => {
      let current: HTMLElement | null = element;
      while (current) {
        const color = parseColor(getComputedStyle(current).backgroundColor);
        if (color && color[3] === 1) return color;
        current = current.parentElement;
      }
      return [255, 255, 255, 1];
    };

    const failures = Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .filter((element) => {
        if (element.closest(".visually-hidden, [hidden], [aria-hidden='true'], :disabled")) {
          return false;
        }
        if (!element.textContent?.trim()) return false;
        if (Array.from(element.children).some((child) => child.textContent?.trim())) {
          return false;
        }
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return (
          rect.width > 0 &&
          rect.height > 0 &&
          style.display !== "none" &&
          style.visibility !== "hidden"
        );
      })
      .flatMap((element) => {
        const foreground = parseColor(getComputedStyle(element).color);
        if (!foreground || foreground[3] !== 1) return [];
        const ratio = contrast(foreground, backgroundFor(element));
        return ratio < 4.5
          ? [
              {
                element: `${element.tagName.toLowerCase()}.${Array.from(element.classList).join(".")}`,
                text: element.textContent?.trim().slice(0, 50),
                ratio: Number(ratio.toFixed(2)),
              },
            ]
          : [];
      });

    const composer = document.querySelector<HTMLTextAreaElement>(".composer textarea");
    if (!composer) throw new Error("Composer textarea is missing.");
    const composerStyle = getComputedStyle(composer);
    const shadowColor = parseColor(composerStyle.boxShadow);
    return {
      failures,
      focusContrast: shadowColor
        ? contrast(shadowColor, backgroundFor(composer))
        : 0,
      focusShadow: composerStyle.boxShadow,
    };
  });

  expect(result.failures).toEqual([]);
  expect(result.focusShadow).not.toBe("none");
  expect(result.focusContrast).toBeGreaterThanOrEqual(3);
});

test("弹窗与操作提示保持文字和焦点对比度", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  const documentTrigger = await uploadDocument(page);

  const successNotice = page.getByRole("status").filter({
    hasText: "索引完成，共生成 3 个片段。",
  });
  const dismissNotice = successNotice.getByRole("button", { name: "关闭提示" });
  await dismissNotice.focus();
  await expect(dismissNotice).toBeFocused();
  await expectVisibleContrast(page, "upload success notice");

  await documentTrigger.click();
  const detailDialog = page.getByRole("dialog", {
    name: "fe04-accessibility-guide.txt",
  });
  const closeDetail = detailDialog.getByRole("button", { name: "关闭文档详情" });
  const deleteTrigger = detailDialog.getByRole("button", { name: "删除文档" });
  await expect(closeDetail).toBeFocused();
  await expectVisibleContrast(page, "document details");

  await deleteTrigger.click();
  const deleteDialog = page.getByRole("dialog", {
    name: "删除文档及全部向量索引？",
  });
  const cancelDelete = deleteDialog.getByRole("button", { name: "取消" });
  await expect(cancelDelete).toBeFocused();
  await expectVisibleContrast(page, "document delete confirmation");
  await cancelDelete.click();
  await expect(deleteTrigger).toBeFocused();

  await updateState(request, { online: false });
  try {
    await deleteTrigger.click();
    await deleteDialog.getByRole("button", { name: "确认删除" }).click();
    await expect(deleteDialog).toBeHidden();
    await expect(
      detailDialog.getByRole("alert").filter({ hasText: "测试后端暂不可用" }),
    ).toBeVisible();
    await expect(deleteTrigger).toBeFocused();
    await expectVisibleContrast(page, "document delete error notice");
  } finally {
    await updateState(request, { online: true });
  }
});
