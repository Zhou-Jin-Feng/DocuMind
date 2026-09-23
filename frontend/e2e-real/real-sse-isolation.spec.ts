import { expect, test, request as playwrightRequest } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

process.env.NO_PROXY = "127.0.0.1,localhost";
process.env.no_proxy = "127.0.0.1,localhost";

const storageKey = "rag-workbench-conversations-v1";
const apiUrl = process.env.DOCUMIND_REAL_API;
if (!apiUrl) {
  throw new Error("DOCUMIND_REAL_API is required for the real SSE isolation test.");
}
const evidenceDir =
  process.env.DOCUMIND_BROWSER_EVIDENCE_DIR || "test-results/browser-real-isolation";

test("real SSE cross-answer and cross-conversation citation isolation", async ({
  page,
}) => {
  fs.mkdirSync(evidenceDir, { recursive: true });
  const api = await playwrightRequest.newContext({ baseURL: apiUrl });
  const token = `R6-BROWSER-${Date.now()}`;
  const filename = `${token}.txt`;
  const content = [
    "R6 浏览器引用隔离安全样例（可丢弃）",
    "",
    `控制项 ${token} 的保留期为 30 天。`,
    `控制项 ${token} 仅用于隔离环境验证。`,
    "如果问题超出本文档范围，系统不应把检索候选直接当作正确回答。",
    "",
  ].join("\n");

  let documentKey: string | undefined;
  const streamResponses: Array<{ url: string; status: number; requestId?: string }> = [];

  try {
    const uploadResponse = await api.post("/api/v1/documents", {
      multipart: {
        file: {
          name: filename,
          mimeType: "text/plain",
          buffer: Buffer.from(content, "utf-8"),
        },
      },
    });
    expect(uploadResponse.ok()).toBeTruthy();
    const upload = (await uploadResponse.json()) as { document_key?: string };
    documentKey = upload.document_key;
    expect(documentKey).toBeTruthy();

    let activeDetail: { status?: string; active_index_id?: string } | null = null;
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const detailResponse = await api.get(`/api/v1/documents/${documentKey}`);
      const detail = (await detailResponse.json()) as {
        status?: string;
        active_index_id?: string;
      };
      if (detail.status === "active") {
        activeDetail = detail;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    expect(activeDetail?.status).toBe("active");

    const oldConversation = [
      {
        id: "real-sse-isolation-old",
        title: "Real SSE isolation old",
        updatedAt: new Date().toISOString(),
        messages: [
          {
            id: "old-user",
            role: "user",
            stage: "done",
            content: "历史隔离问题",
            sources: [],
          },
          {
            id: "old-answer",
            role: "assistant",
            stage: "done",
            content: "历史回答 [文档1]。",
            sources: [
              {
                rank: 1,
                source: "old-source.txt",
                excerpt: "old source excerpt",
                chunk_id: "old-1",
              },
            ],
          },
        ],
      },
    ];

    await page.addInitScript(
      ({ key, value }) => localStorage.setItem(key, value),
      { key: storageKey, value: JSON.stringify(oldConversation) },
    );
    page.on("response", (response) => {
      if (response.url().includes("/api/v1/chat/stream")) {
        streamResponses.push({
          url: response.url(),
          status: response.status(),
          requestId: response.headers()["x-request-id"],
        });
      }
    });

    await page.goto("/");
    await expect(page.getByText("服务就绪", { exact: true })).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByRole("button", { name: "查看引用文档1" })).toHaveCount(1);
    const assistantMessages = page.locator(".message-assistant");
    await expect(assistantMessages).toHaveCount(1);
    await expect(page.locator(".source-item-highlighted")).toHaveCount(0);

    await page
      .getByPlaceholder("向知识库提问")
      .fill(`控制项 ${token} 的保留期是多少天？`);
    await page.getByRole("button", { name: "发送", exact: true }).click();

    await expect(assistantMessages).toHaveCount(2, { timeout: 120_000 });
    await expect(page.getByRole("button", { name: "发送", exact: true })).toBeVisible({
      timeout: 120_000,
    });
    const newAssistant = assistantMessages.nth(1);
    const newAnswerText = await newAssistant.innerText();
    const newCitationChipCount = await newAssistant.locator("button.citation-chip").count();
    const newCitationLinkCount = await newAssistant.locator("button.citation-link").count();
    const generationErrorObserved =
      newAnswerText.includes("系统暂时无法完成回答") ||
      newAnswerText.includes("请稍后重试") ||
      newAnswerText.includes("暂时无法");
    expect(newCitationLinkCount).toBeGreaterThan(0);
    await expect(page.locator(".source-item-highlighted")).toHaveCount(0);

    await newAssistant.locator("button.citation-link").first().click();
    const sourcesPanel = page.getByRole("complementary", { name: "引用来源" });
    await expect(sourcesPanel).toContainText(filename);
    await expect(sourcesPanel).not.toContainText("old-source.txt");
    let highlightCheckSkipped = false;
    if (newCitationChipCount > 0) {
      await newAssistant.locator("button.citation-chip").first().click();
      const highlighted = page.locator(".source-item-highlighted");
      await expect(highlighted).toHaveCount(1, { timeout: 15_000 });
      await expect(highlighted).toContainText(filename);
    } else {
      highlightCheckSkipped = true;
      await expect(page.locator(".source-item-highlighted")).toHaveCount(0);
    }
    await page.screenshot({
      path: path.join(evidenceDir, "after-real-answer.png"),
      fullPage: true,
    });

    await page.locator(".new-chat-button").click();
    await expect(page.locator("button.citation-chip")).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(page.locator("button.citation-link")).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(page.locator(".source-item-highlighted")).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(page.locator(".source-item", { hasText: "old-source.txt" })).toHaveCount(0);
    await page.screenshot({
      path: path.join(evidenceDir, "after-new-conversation.png"),
      fullPage: true,
    });

    fs.writeFileSync(
      path.join(evidenceDir, "browser-isolation-evidence.json"),
      JSON.stringify(
        {
          token,
          filename,
          documentKey,
          activeIndexId: activeDetail?.active_index_id,
          streamResponses,
          oldCitationVisible: true,
          newAnswerText,
          generationErrorObserved,
          newCitationChipCount,
          newCitationLinkCount,
          highlightCheckSkipped,
          sourcesPanelContainsNewSource: true,
          sourcesPanelContainsOldSource: false,
          newConversationClean: true,
        },
        null,
        2,
      ),
      "utf-8",
    );
  } finally {
    if (documentKey) {
      await api.delete(`/api/v1/documents/${documentKey}`).catch(() => undefined);
    }
    await api.dispose();
  }
});
