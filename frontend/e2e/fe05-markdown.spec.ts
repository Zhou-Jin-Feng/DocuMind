import { expect, test, type APIRequestContext } from "@playwright/test";

const apiUrl = "http://127.0.0.1:4174";
const storageKey = "rag-workbench-conversations-v1";

function seededConversations() {
  const code = [
    "```python",
    "def answer(value):",
    "    return value",
    "```",
    "",
    "```ts",
    "const answer: string = \"ok\";",
    "```",
    "",
    "```json",
    "{\"answer\": true}",
    "```",
    "",
    "```bash",
    "echo answer",
    "```",
    "",
    "```js",
    "const alias = 1",
    "```",
    "",
    "```unknown-language",
    "unknown syntax",
    "```",
    "",
    "```",
    "plain text block",
    "```",
    "",
    "`[文档1]`",
    "",
    "[链接中的 [文档1]](https://example.com)",
  ].join("\n");
  return [
    {
      id: "fe05-conversation-a",
      title: "FE-05 引用与代码 A",
      updatedAt: "2026-09-21T01:00:00.000Z",
      messages: [
        { id: "fe05-question-a", role: "user", content: "问题 A", stage: "done", sources: [] },
        {
          id: "fe05-answer-a",
          role: "assistant",
          content: "有效引用 [文档1] 和 [文档2]，越界 [文档3]。\n\n" + code,
          stage: "done",
          sources: [
            { rank: 1, source: "source-a-1.txt", excerpt: "回答 A 的第一来源", chunk_id: "a-1", page_number: 1 },
            { rank: 2, source: "source-a-2.txt", excerpt: "回答 A 的第二来源", chunk_id: "a-2", page_number: 2 },
          ],
        },
        {
          id: "fe05-question-b",
          role: "user",
          content: "问题 B",
          stage: "done",
          sources: [],
        },
        {
          id: "fe05-answer-b",
          role: "assistant",
          content: "另一个回答也使用 [文档1]。",
          stage: "done",
          sources: [
            { rank: 1, source: "source-b-1.txt", excerpt: "回答 B 的第一来源", chunk_id: "b-1", page_number: 3 },
          ],
        },
      ],
    },
  ];
}

async function updateState(request: APIRequestContext, state: Record<string, unknown>) {
  const response = await request.post(`${apiUrl}/__e2e/state`, { data: state });
  expect(response.ok()).toBeTruthy();
}

test.beforeEach(async ({ request }) => {
  const response = await request.post(`${apiUrl}/__e2e/reset`);
  expect(response.ok()).toBeTruthy();
});

test("只把回答来源中的有效正文引用转换为 chip 并定位到所属回答", async ({ page }) => {
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, value), {
    key: storageKey,
    value: JSON.stringify(seededConversations()),
  });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "查看引用文档1" })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "查看引用文档2" })).toHaveCount(1);
  await expect(page.locator(".message-assistant").first()).toContainText("[文档3]");
  await expect(page.locator(".message-assistant").first()).toContainText("[文档1]");
  await expect(page.locator("a[href=\"https://example.com\"]")).toContainText("[文档1]");

  const firstAnswer = page.locator(".message-assistant").nth(0);
  await firstAnswer.getByRole("button", { name: "查看引用文档1" }).click();
  await expect(page.locator(".source-item-highlighted")).toContainText("source-a-1.txt");
  await expect(page.locator(".source-item-highlighted")).toHaveAttribute("data-source-rank", "1");

  const secondAnswer = page.locator(".message-assistant").nth(1);
  await secondAnswer.getByRole("button", { name: "查看引用文档1" }).click();
  await expect(page.locator(".source-item-highlighted")).toContainText("source-b-1.txt");
  await expect(page.locator(".source-item-highlighted")).not.toContainText("source-a-1.txt");
});

test("高亮支持常用语言与 aliases，未知/无语言安全退化", async ({ page }) => {
  await page.addInitScript(({ key, value }) => localStorage.setItem(key, value), {
    key: storageKey,
    value: JSON.stringify(seededConversations()),
  });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  const codeBlocks = page.locator(".message-assistant pre code");
  await expect(codeBlocks).toHaveCount(7);
  const classes = await codeBlocks.evaluateAll((nodes) => nodes.map((node) => node.className));
  expect(classes.filter((value) => value.includes("hljs"))).toHaveLength(6);
  for (let index = 0; index < 5; index += 1) {
    await expect(codeBlocks.nth(index).locator("span")).not.toHaveCount(0);
  }
  await expect(codeBlocks.nth(5).locator("span")).toHaveCount(0);
  await expect(codeBlocks.nth(6).locator("span")).toHaveCount(0);
  await expect(codeBlocks.nth(5).locator("span")).toHaveCount(0);
  await expect(codeBlocks.nth(6).locator("span")).toHaveCount(0);
});

test("有文档无对话时建议按钮只填充问题并聚焦输入框", async ({ page, request }) => {
  await updateState(request, {
    documents: [{
      document_key: "fe05-empty-document",
      display_name: "empty-state.txt",
      status: "active",
      chunk_count: 3,
      file_type: ".txt",
      file_size_bytes: 123,
      active_index_id: "empty-index",
      active_version_id: "empty-version",
      version_count: 1,
      error_type: null,
      created_at: "2026-09-21T01:00:00.000Z",
      updated_at: "2026-09-21T01:00:00.000Z",
    }],
  });
  await page.addInitScript((key) => localStorage.removeItem(key), storageKey);
  await page.goto("/");
  await expect(page.getByText("暂无对话", { exact: true })).toBeVisible();
  const prompt = page.getByRole("button", { name: "这份知识库主要讲什么？" });
  await prompt.click();
  await expect(page.getByPlaceholder("向知识库提问")).toHaveValue("这份知识库主要讲什么？");
  await expect(page.getByPlaceholder("向知识库提问")).toBeFocused();
  const response = await request.get(`${apiUrl}/__e2e/state`);
  const state = (await response.json()) as { streamRequests: number };
  expect(state.streamRequests).toBe(0);
});
