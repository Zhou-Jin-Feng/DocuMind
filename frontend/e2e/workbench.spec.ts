import { expect, test, type APIRequestContext } from "@playwright/test";

const apiUrl = "http://127.0.0.1:4174";

async function updateState(
  request: APIRequestContext,
  state: Record<string, unknown>,
) {
  const response = await request.post(`${apiUrl}/__e2e/state`, { data: state });
  expect(response.ok()).toBeTruthy();
}

test.beforeEach(async ({ request }) => {
  const response = await request.post(`${apiUrl}/__e2e/reset`);
  expect(response.ok()).toBeTruthy();
});

test("后端不可用时给出明确状态，并在恢复后自动刷新", async ({
  page,
}) => {
  const apiPattern = `${apiUrl}/api/v1/**`;
  await page.route(apiPattern, (route) => route.abort("connectionrefused"));
  await page.goto("/");

  await expect(page.getByText("服务未就绪", { exact: true })).toBeVisible();
  await expect(page.getByText("文档服务不可用", { exact: true })).toBeVisible();
  await expect(page.getByText("配置不可用", { exact: true })).toBeVisible();

  await page.unroute(apiPattern);

  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
  await expect(page.getByText("知识库为空", { exact: true })).toBeVisible();
  await expect(page.getByText("ollama · deepseek", { exact: true })).toBeVisible();
});

test("上传文档后展示索引结果", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: "guide.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("RAG 通过检索外部知识增强模型回答。", "utf-8"),
  });

  await expect(page.getByText("索引完成，共生成 3 个 chunks。", { exact: true })).toBeVisible();
  await expect(page.getByTitle("guide.txt")).toBeVisible();
  await expect(page.getByText("1 个文档", { exact: true })).toBeVisible();
});

test("查看详情、重新索引并删除文档", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: "guide.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("RAG 文档管理测试。", "utf-8"),
  });
  await page.getByRole("button", { name: "查看文档 guide.txt" }).click();

  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("heading", { name: "guide.txt" })).toBeVisible();
  await expect(page.getByText("1 个版本", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "索引历史" })).toBeVisible();
  await expect(page.getByText("版本 1", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "重新建立索引" }).click();
  await expect(
    page.getByText("索引重建完成，共生成 3 个 chunks。", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "删除文档" }).click();
  await expect(
    page.getByText("删除文档及全部向量索引？", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "确认删除" }).click();

  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(
    page.getByText("文档及向量索引已删除。", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("知识库为空", { exact: true })).toBeVisible();
  const response = await request.get(`${apiUrl}/__e2e/state`);
  const state = (await response.json()) as {
    reindexCount: number;
    deleteCount: number;
  };
  expect(state.reindexCount).toBe(1);
  expect(state.deleteCount).toBe(1);
});

test("流式问答展示回答和引用来源", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();

  await page.getByPlaceholder("向知识库提问").fill("什么是 RAG？");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("RAG 是检索增强生成技术。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "1 条引用来源" })).toBeVisible();
  await expect(page.getByText("guide.txt", { exact: true })).toBeVisible();
  await expect(
    page.getByText("RAG 通过检索外部知识增强模型回答。", { exact: true }),
  ).toBeVisible();
});

test("停止生成会中止浏览器中的流式请求", async ({ page, request }) => {
  await updateState(request, { streamMode: "slow" });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();

  await page.getByPlaceholder("向知识库提问").fill("生成一个很长的回答");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "停止" })).toBeVisible();
  await expect(page.getByText(/部分回答/)).toBeVisible();

  await page.getByRole("button", { name: "停止" }).click();

  await expect(page.getByRole("button", { name: "发送" })).toBeVisible();
  await expect
    .poll(async () => {
      const response = await request.get(`${apiUrl}/__e2e/state`);
      const state = (await response.json()) as { abortedStreams: number };
      return state.abortedStreams;
    })
    .toBe(1);
});
