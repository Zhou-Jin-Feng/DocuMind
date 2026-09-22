import { mkdir, rm } from "node:fs/promises";
import path from "node:path";
import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const apiUrl = "http://127.0.0.1:4174";
const storageKey = "rag-workbench-conversations-v1";
const artifactDirectory = path.resolve(
  process.cwd(),
  "../artifacts/frontend-3.1.0/fe04/layout-matrix",
);
const conversationTitle =
  "这是一个用于 FE-04 布局矩阵的超长中文会话标题-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789";
const documentName =
  "DocuMind-FE04-超长中文文档名-用于验证字号提升后状态与操作入口-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789.txt";
const wideTableCell = `WIDETABLE${"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".repeat(24)}`;
const longCodeLine = `const layoutEvidence = "${"long-code-segment-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".repeat(20)}";`;

const viewports = [
  { name: "desktop", width: 1440, height: 900, compactSources: false },
  { name: "breakpoint", width: 860, height: 900, compactSources: true },
  { name: "mobile", width: 390, height: 844, compactSources: true },
  { name: "minimum", width: 320, height: 844, compactSources: true },
  { name: "zoom-200-layout", width: 720, height: 450, compactSources: true },
] as const;

const overlapPairs = [
  {
    label: "workspace heading/actions",
    first: ".workspace-header > div:first-child",
    second: ".header-actions",
  },
  {
    label: "conversation select/delete",
    first: ".conversation-item .conversation-select",
    second: ".conversation-item .conversation-delete",
  },
  {
    label: "document copy/status",
    first: ".document-item .document-copy",
    second: ".document-item .document-status",
  },
  {
    label: "composer input/send",
    first: ".composer textarea",
    second: ".composer .send-button",
  },
  {
    label: "sources title/close",
    first: ".sources-panel > header > div",
    second: ".sources-panel > header > .sources-close",
  },
  {
    label: "document title/close",
    first: ".document-dialog .dialog-header > div",
    second: ".document-dialog .dialog-header > .icon-button",
  },
  {
    label: "document actions",
    first: ".document-actions > .secondary-button",
    second: ".document-actions > .danger-button",
  },
  {
    label: "confirmation icon/copy",
    first: ".conversation-confirm-dialog .confirmation-icon",
    second: ".conversation-confirm-dialog .confirmation-copy",
  },
  {
    label: "confirmation actions",
    first: ".confirmation-actions > .secondary-button",
    second: ".confirmation-actions > .danger-button",
  },
] as const;

const workspacePairs = [
  "workspace heading/actions",
  "conversation select/delete",
  "document copy/status",
  "composer input/send",
];

function seededConversation() {
  return [
    {
      id: "fe04-layout-conversation",
      title: conversationTitle,
      updatedAt: "2026-09-21T01:00:00.000Z",
      messages: [
        {
          id: "fe04-layout-question",
          role: "user",
          content:
            "请验证超长中文、宽表格、长代码与引用来源在所有目标视口都不会撑破页面。",
          stage: "done",
          sources: [],
        },
        {
          id: "fe04-layout-answer",
          role: "assistant",
          content: [
            "这是一段用于验证中文换行、行高和有效信息可读性的回答。",
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
              source:
                "超长来源文件名-验证来源标题不会挤压关闭入口-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789.txt",
              excerpt:
                "第一条来源包含足够长的中文摘要，用于检查窄屏单列、断点双列和桌面侧栏中的换行与局部滚动行为。",
              chunk_id: "fe04-layout-source-1",
              page_number: 390,
              distance: 0.125,
              rerank_score: 0.9876,
            },
            {
              rank: 2,
              source:
                "第二条超长来源文件名-验证多卡片布局-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789.txt",
              excerpt:
                "第二条来源保证 860px 抽屉使用双列时也能实际检查标题、指标与关闭按钮，而不是只验证空状态。",
              chunk_id: "fe04-layout-source-2",
              page_number: 844,
              distance: 0.25,
              fusion_score: 0.76543,
            },
          ],
        },
      ],
    },
  ];
}

const seededDocument = {
  document_key: "fe04-layout-document",
  display_name: documentName,
  status: "active",
  chunk_count: 128,
  file_type: ".txt",
  file_size_bytes: 1_234_567,
  active_index_id: "fe04-layout-index",
  active_version_id: "fe04-layout-version-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  version_count: 1,
  error_type: null,
  created_at: "2026-09-21T01:00:00.000Z",
  updated_at: "2026-09-21T01:00:00.000Z",
};

async function updateState(
  request: APIRequestContext,
  state: Record<string, unknown>,
): Promise<void> {
  const response = await request.post(`${apiUrl}/__e2e/state`, { data: state });
  expect(response.ok()).toBeTruthy();
}

async function loadLayoutFixture(
  page: Page,
  request: APIRequestContext,
): Promise<void> {
  await updateState(request, { documents: [seededDocument] });
  await page.addInitScript(
    ({ key, value }) => localStorage.setItem(key, value),
    { key: storageKey, value: JSON.stringify(seededConversation()) },
  );
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  await expect(page.locator(".message")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: `查看文档 ${documentName}`, exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "2 条引用来源" })).toBeVisible();
}

async function expectDeterministicLayout(
  page: Page,
  state: string,
  requiredPairs: string[],
): Promise<void> {
  const result = await page.evaluate((pairs) => {
    const visible = (element: Element): element is HTMLElement => {
      if (!(element instanceof HTMLElement)) return false;
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        rect.width > 0 &&
        rect.height > 0
      );
    };
    const label = (element: HTMLElement) =>
      (
        element.getAttribute("aria-label") ||
        element.getAttribute("title") ||
        element.textContent ||
        element.className
      )
        .trim()
        .replace(/\s+/g, " ")
        .slice(0, 80);
    const rectangle = (element: HTMLElement) => {
      const rect = element.getBoundingClientRect();
      return {
        left: Math.round(rect.left * 10) / 10,
        right: Math.round(rect.right * 10) / 10,
        top: Math.round(rect.top * 10) / 10,
        bottom: Math.round(rect.bottom * 10) / 10,
        width: Math.round(rect.width * 10) / 10,
        height: Math.round(rect.height * 10) / 10,
      };
    };
    const intersects = (
      first: ReturnType<typeof rectangle>,
      second: ReturnType<typeof rectangle>,
    ) =>
      Math.min(first.right, second.right) - Math.max(first.left, second.left) > 0.5 &&
      Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top) > 0.5;

    const viewportWidth = document.documentElement.clientWidth;
    const controls = Array.from(
      document.querySelectorAll<HTMLElement>(
        "button:not([hidden]), textarea:not([hidden]), [role='dialog'], .sources-panel, .message-body pre, .message-body table",
      ),
    ).filter(visible);
    const outside = controls
      .map((element) => ({
        label: label(element),
        rect: rectangle(element),
      }))
      .filter(({ rect }) => rect.left < -1 || rect.right > viewportWidth + 1);

    const checkedPairs: string[] = [];
    const overlaps: Array<{
      label: string;
      first: { label: string; rect: ReturnType<typeof rectangle> };
      second: { label: string; rect: ReturnType<typeof rectangle> };
    }> = [];
    for (const pair of pairs) {
      const first = document.querySelector(pair.first);
      const second = document.querySelector(pair.second);
      if (!first || !second || !visible(first) || !visible(second)) continue;
      checkedPairs.push(pair.label);
      const firstRect = rectangle(first);
      const secondRect = rectangle(second);
      if (intersects(firstRect, secondRect)) {
        overlaps.push({
          label: pair.label,
          first: { label: label(first), rect: firstRect },
          second: { label: label(second), rect: secondRect },
        });
      }
    }

    return {
      viewportWidth,
      documentOverflow:
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
      bodyOverflow: document.body.scrollWidth - document.documentElement.clientWidth,
      outside,
      checkedPairs,
      overlaps,
    };
  }, overlapPairs);

  const evidence = `${state}: ${JSON.stringify(result, null, 2)}`;
  expect(result.documentOverflow, evidence).toBeLessThanOrEqual(1);
  expect(result.bodyOverflow, evidence).toBeLessThanOrEqual(1);
  expect(result.outside, evidence).toEqual([]);
  expect(result.overlaps, evidence).toEqual([]);
  for (const requiredPair of requiredPairs) {
    expect(result.checkedPairs, evidence).toContain(requiredPair);
  }
}

async function expectMarkdownUsesLocalHorizontalScroll(page: Page): Promise<void> {
  const result = await page.evaluate(() => {
    const nodes = Array.from(
      document.querySelectorAll<HTMLElement>(".message-body pre, .message-body table"),
    );
    return nodes.map((element) => {
      const owner = element.closest<HTMLElement>(".message-body");
      const rect = element.getBoundingClientRect();
      const ownerRect = owner?.getBoundingClientRect();
      const maximumScrollLeft = element.scrollWidth - element.clientWidth;
      const initialScrollLeft = element.scrollLeft;
      element.scrollLeft = maximumScrollLeft;
      const reachedScrollLeft = element.scrollLeft;
      element.scrollLeft = initialScrollLeft;
      return {
        tag: element.tagName.toLowerCase(),
        overflowX: getComputedStyle(element).overflowX,
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        maximumScrollLeft,
        reachedScrollLeft,
        containedByMessage:
          Boolean(ownerRect) &&
          rect.left >= (ownerRect?.left ?? 0) - 1 &&
          rect.right <= (ownerRect?.right ?? 0) + 1,
      };
    });
  });

  expect(result.map(({ tag }) => tag).sort()).toEqual(["pre", "table"]);
  for (const item of result) {
    expect(item.maximumScrollLeft, JSON.stringify(item)).toBeGreaterThan(1);
    expect(item.reachedScrollLeft, JSON.stringify(item)).toBeGreaterThan(0);
    expect(["auto", "scroll"], JSON.stringify(item)).toContain(item.overflowX);
    expect(item.containedByMessage, JSON.stringify(item)).toBe(true);
  }
}

async function capture(
  page: Page,
  name: string,
  fullPage = false,
): Promise<void> {
  await page.screenshot({
    path: path.join(artifactDirectory, `${name}.png`),
    fullPage,
    animations: "disabled",
    caret: "hide",
  });
}

test.beforeAll(async () => {
  await rm(artifactDirectory, { recursive: true, force: true });
  await mkdir(artifactDirectory, { recursive: true });
});

test.beforeEach(async ({ request }) => {
  const response = await request.post(`${apiUrl}/__e2e/reset`);
  expect(response.ok()).toBeTruthy();
});

for (const viewport of viewports) {
  test(`${viewport.name} 完成确定性布局状态矩阵`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await loadLayoutFixture(page, request);

    if (viewport.compactSources) {
      await expect(page.getByRole("dialog", { name: "引用来源" })).toHaveCount(0);
      await expect(page.getByRole("complementary", { name: "引用来源" })).toHaveCount(0);
    } else {
      await expect(page.getByRole("complementary", { name: "引用来源" })).toBeVisible();
      await expect(page.getByRole("dialog", { name: "引用来源" })).toHaveCount(0);
    }
    await expectMarkdownUsesLocalHorizontalScroll(page);
    await expectDeterministicLayout(page, `${viewport.name}/workspace`, workspacePairs);
    await capture(
      page,
      `${viewport.width}x${viewport.height}-workspace`,
      viewport.compactSources,
    );

    if (!viewport.compactSources) {
      await page.getByRole("button", { name: "关闭引用来源" }).click();
      await expect(page.getByRole("complementary", { name: "引用来源" })).toHaveCount(0);
    }
    await page.getByRole("button", { name: "2 条引用来源" }).click();
    if (viewport.compactSources) {
      await expect(page.getByRole("dialog", { name: "引用来源" })).toBeVisible();
      await expect(page.getByRole("complementary", { name: "引用来源" })).toHaveCount(0);
    } else {
      await expect(page.getByRole("complementary", { name: "引用来源" })).toBeVisible();
      await expect(page.getByRole("dialog", { name: "引用来源" })).toHaveCount(0);
    }
    await expect(page.locator(".source-item")).toHaveCount(2);
    await expectDeterministicLayout(page, `${viewport.name}/sources`, [
      ...workspacePairs,
      "sources title/close",
    ]);
    await capture(
      page,
      `${viewport.width}x${viewport.height}-sources`,
    );
    await page.getByRole("button", { name: "关闭引用来源" }).click();
    await expect(page.locator(".sources-panel")).toHaveCount(0);

    const documentTrigger = page.getByRole("button", {
      name: `查看文档 ${documentName}`,
      exact: true,
    });
    await documentTrigger.click();
    const documentDialog = page.getByRole("dialog", { name: documentName });
    await expect(documentDialog).toBeVisible();
    await expectDeterministicLayout(page, `${viewport.name}/document-dialog`, [
      ...workspacePairs,
      "document title/close",
      "document actions",
    ]);
    await capture(
      page,
      `${viewport.width}x${viewport.height}-document-dialog`,
    );

    await documentDialog
      .getByRole("button", { name: "删除文档", exact: true })
      .click();
    const deleteDialog = page.getByRole("dialog", {
      name: "删除文档及全部向量索引？",
    });
    await expect(deleteDialog).toBeVisible();
    await expect(page.locator('[role="dialog"]')).toHaveCount(2);
    await expectDeterministicLayout(page, `${viewport.name}/document-delete`, [
      ...workspacePairs,
      "document title/close",
      "document actions",
      "confirmation icon/copy",
      "confirmation actions",
    ]);
    await capture(
      page,
      `${viewport.width}x${viewport.height}-document-delete`,
    );
    await deleteDialog.getByRole("button", { name: "取消" }).click();
    await expect(deleteDialog).toBeHidden();
    await documentDialog.getByRole("button", { name: "关闭文档详情" }).click();
    await expect(documentDialog).toBeHidden();

    await page.getByRole("button", { name: "清空当前对话" }).click();
    const conversationDialog = page.getByRole("dialog", {
      name: "清空当前对话？",
    });
    await expect(conversationDialog).toBeVisible();
    await expectDeterministicLayout(page, `${viewport.name}/conversation-confirm`, [
      ...workspacePairs,
      "confirmation icon/copy",
      "confirmation actions",
    ]);
    await capture(
      page,
      `${viewport.width}x${viewport.height}-conversation-confirm`,
    );
    await conversationDialog.getByRole("button", { name: "取消" }).click();
    await expect(conversationDialog).toBeHidden();
  });
}
