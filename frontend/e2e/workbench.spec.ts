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

test("上传文档后展示索引结果", async ({ page, request }) => {
  await updateState(request, { uploadDelayMs: 600 });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: "guide.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("RAG 通过检索外部知识增强模型回答。", "utf-8"),
  });

  await expect(page.getByText("解析、切分与向量化", { exact: true })).toBeVisible();
  await expect(page.getByText("索引完成，共生成 3 个片段。", { exact: true })).toBeVisible();
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
    page.getByText("索引重建完成，共生成 3 个片段。", { exact: true }),
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
  const storageKey = "rag-workbench-conversations-v1";
  const question = "生成一个很长的回答";
  await page.addInitScript((key) => {
    const nativeSetItem = Storage.prototype.setItem;
    let conversationWrites = 0;
    Storage.prototype.setItem = function setItem(storageKey, value) {
      if (storageKey === key) conversationWrites += 1;
      nativeSetItem.call(this, storageKey, value);
    };
    (
      window as Window & {
        __conversationStorageWriteCount?: () => number;
      }
    ).__conversationStorageWriteCount = () => conversationWrites;
  }, storageKey);
  await updateState(request, { streamMode: "slow" });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();

  const writesBeforeSend = await page.evaluate(() => {
    const getWriteCount = (
      window as Window & {
        __conversationStorageWriteCount?: () => number;
      }
    ).__conversationStorageWriteCount;
    if (!getWriteCount) throw new Error("Conversation storage probe is not installed.");
    return getWriteCount();
  });
  await page.getByPlaceholder("向知识库提问").fill(question);
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "停止" })).toBeVisible();
  await expect(page.getByText(/部分回答/)).toBeVisible();
  const answerParagraph = page.locator(".message-assistant .message-body p").last();
  const firstVisibleText = (await answerParagraph.textContent()) ?? "";
  await expect
    .poll(async () => ((await answerParagraph.textContent()) ?? "").length)
    .toBeGreaterThanOrEqual(firstVisibleText.length + 3);
  const writesDuringStream = await page.evaluate(() => {
    const getWriteCount = (
      window as Window & {
        __conversationStorageWriteCount?: () => number;
      }
    ).__conversationStorageWriteCount;
    if (!getWriteCount) throw new Error("Conversation storage probe is not installed.");
    return getWriteCount();
  });
  expect(writesDuringStream).toBe(writesBeforeSend);

  await page.getByRole("button", { name: "停止" }).click();

  await expect(page.getByRole("button", { name: "发送" })).toBeVisible();
  const stoppedDomText = (await answerParagraph.textContent()) ?? "";
  expect(stoppedDomText.length).toBeGreaterThanOrEqual(firstVisibleText.length + 3);
  await expect
    .poll(() =>
      page.evaluate(
        ({ key, expectedQuestion }) => {
          const raw = localStorage.getItem(key);
          if (!raw) return null;
          const conversations = JSON.parse(raw) as Array<{
            messages: Array<{
              role: "user" | "assistant";
              content: string;
              stage: string;
            }>;
          }>;
          const conversation = conversations.find((item) =>
            item.messages.some(
              (message) =>
                message.role === "user" && message.content === expectedQuestion,
            ),
          );
          const answer = conversation?.messages
            .filter((message) => message.role === "assistant")
            .at(-1);
          return answer ? { content: answer.content, stage: answer.stage } : null;
        },
        { key: storageKey, expectedQuestion: question },
      ),
    )
    .toEqual({ content: stoppedDomText, stage: "done" });
  const writesAfterStop = await page.evaluate(() => {
    const getWriteCount = (
      window as Window & {
        __conversationStorageWriteCount?: () => number;
      }
    ).__conversationStorageWriteCount;
    if (!getWriteCount) throw new Error("Conversation storage probe is not installed.");
    return getWriteCount();
  });
  expect(writesAfterStop).toBeGreaterThan(writesBeforeSend);
  await expect
    .poll(async () => {
      const response = await request.get(`${apiUrl}/__e2e/state`);
      const state = (await response.json()) as { abortedStreams: number };
      return state.abortedStreams;
    })
    .toBe(1);

  await page.reload();
  await expect(page.getByText(stoppedDomText, { exact: true })).toBeVisible();
});

test("本地保存、切换并清空对话历史", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();

  await page.getByPlaceholder("向知识库提问").fill("什么是 RAG？");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("RAG 是检索增强生成技术。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "打开对话 什么是 RAG？" })).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => localStorage.getItem("rag-workbench-conversations-v1")),
    )
    .not.toBeNull();

  await page.reload();
  await expect(page.getByText("RAG 是检索增强生成技术。", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "新建对话" }).click();
  await expect(page.getByText("暂无对话", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "打开对话 什么是 RAG？" }).click();
  await expect(page.getByText("RAG 是检索增强生成技术。", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "清空当前对话" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "清空对话", exact: true }).click();
  await expect(page.getByText("暂无对话", { exact: true })).toBeVisible();
  await expect(page.getByText("暂无历史对话", { exact: true })).toBeVisible();
});

test("切换会话后旧流不会污染新回答、状态或来源", async ({
  page,
  request,
}) => {
  const questionA = "A 慢流问题";
  const questionB = "B 正常问题";
  await page.addInitScript(() => {
    const testWindow = window as typeof window & {
      __e2eFirstChatAbortPending?: boolean;
      __e2eReleaseFirstChatAbort?: () => void;
    };
    const nativeFetch = window.fetch.bind(window);
    let chatRequestCount = 0;

    testWindow.fetch = (input, init) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (!url.endsWith("/api/v1/chat/stream")) {
        return nativeFetch(input, init);
      }

      chatRequestCount += 1;
      if (chatRequestCount !== 1 || !init?.signal) {
        return nativeFetch(input, init);
      }

      const applicationSignal = init.signal;
      const deferredAbort = new AbortController();
      let abortRequested = false;
      let abortReason: unknown;
      testWindow.__e2eReleaseFirstChatAbort = () => {
        if (!abortRequested || deferredAbort.signal.aborted) return;
        deferredAbort.abort(abortReason);
      };
      applicationSignal.addEventListener(
        "abort",
        () => {
          abortRequested = true;
          abortReason = applicationSignal.reason;
          testWindow.__e2eFirstChatAbortPending = true;
        },
        { once: true },
      );

      return nativeFetch(input, { ...init, signal: deferredAbort.signal });
    };
  });
  await updateState(request, { streamMode: "conversation-race" });
  await page.goto("/");
  await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();

  const composer = page.getByPlaceholder("向知识库提问");
  await composer.fill(questionA);
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("A 部分回答", { exact: true })).toBeVisible();
  await expect(page.getByText("source-a.txt", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "停止" })).toBeVisible();

  await page.getByRole("button", { name: "新建对话" }).click();
  await composer.fill(questionB);
  await page.getByRole("button", { name: "发送" }).click();

  await expect
    .poll(() =>
      page.evaluate(
        () =>
          Boolean(
            (window as typeof window & {
              __e2eFirstChatAbortPending?: boolean;
            }).__e2eFirstChatAbortPending,
          ),
      ),
    )
    .toBe(true);
  await expect
    .poll(async () => {
      const response = await request.get(`${apiUrl}/__e2e/state`);
      const state = (await response.json()) as {
        streamRequests: number;
        abortedStreams: number;
        streamQuestions: string[];
        raceBPending: boolean;
      };
      return state;
    })
    .toMatchObject({
      streamRequests: 2,
      abortedStreams: 0,
      streamQuestions: [questionA, questionB],
      raceBPending: true,
    });

  await expect(page.getByRole("button", { name: "停止" })).toBeVisible();
  await expect(page.getByRole("button", { name: "发送" })).toBeHidden();
  await expect(page.getByText("source-b.txt", { exact: true })).toBeVisible();
  await expect(page.getByText("source-a.txt", { exact: true })).toBeHidden();

  await page.evaluate(() => {
    const releaseAbort = (
      window as typeof window & {
        __e2eReleaseFirstChatAbort?: () => void;
      }
    ).__e2eReleaseFirstChatAbort;
    if (!releaseAbort) throw new Error("First chat abort gate was not installed.");
    releaseAbort();
  });
  await expect
    .poll(async () => {
      const response = await request.get(`${apiUrl}/__e2e/state`);
      const state = (await response.json()) as {
        abortedStreams: number;
        raceBPending: boolean;
      };
      return state;
    })
    .toMatchObject({ abortedStreams: 1, raceBPending: true });
  await expect(page.getByRole("button", { name: "停止" })).toBeVisible();
  await expect(page.getByRole("button", { name: "发送" })).toBeHidden();
  await expect(page.getByText("source-b.txt", { exact: true })).toBeVisible();
  await expect(page.getByText("source-a.txt", { exact: true })).toBeHidden();

  const releaseResponse = await request.post(`${apiUrl}/__e2e/release-race-b`);
  expect(releaseResponse.ok()).toBeTruthy();
  await expect(page.getByText("B 完整回答", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "发送" })).toBeVisible();
  await expect(page.getByRole("button", { name: "停止" })).toBeHidden();
  await expect(page.getByText("source-b.txt", { exact: true })).toBeVisible();
  await expect(page.getByText("source-a.txt", { exact: true })).toBeHidden();

  await expect
    .poll(() =>
      page.evaluate(
        ({ storageKey, firstQuestion, secondQuestion }) => {
          const raw = localStorage.getItem(storageKey);
          if (!raw) return null;
          const conversations = JSON.parse(raw) as Array<{
            messages: Array<{
              role: "user" | "assistant";
              content: string;
              stage: string;
              sources: Array<{ source: string }>;
            }>;
          }>;
          const answerFor = (question: string) => {
            const conversation = conversations.find((item) =>
              item.messages.some(
                (message) => message.role === "user" && message.content === question,
              ),
            );
            const answer = conversation?.messages.find(
              (message) => message.role === "assistant",
            );
            return answer
              ? {
                  content: answer.content,
                  stage: answer.stage,
                  source: answer.sources[0]?.source ?? null,
                }
              : null;
          };
          return {
            answerA: answerFor(firstQuestion),
            answerB: answerFor(secondQuestion),
          };
        },
        {
          storageKey: "rag-workbench-conversations-v1",
          firstQuestion: questionA,
          secondQuestion: questionB,
        },
      ),
    )
    .toEqual({
      answerA: {
        content: "A 部分回答",
        stage: "done",
        source: "source-a.txt",
      },
      answerB: {
        content: "B 完整回答",
        stage: "done",
        source: "source-b.txt",
      },
    });

  await page.getByRole("button", { name: `打开对话 ${questionA}` }).click();
  await expect(page.getByText("A 部分回答", { exact: true })).toBeVisible();
  await expect(page.getByText("B 完整回答", { exact: true })).toBeHidden();
  await expect(page.getByText("source-a.txt", { exact: true })).toBeVisible();
  await expect(page.getByText("source-b.txt", { exact: true })).toBeHidden();
  await expect(page.getByRole("button", { name: "发送" })).toBeVisible();
  await expect(page.getByRole("button", { name: "停止" })).toBeHidden();
});
