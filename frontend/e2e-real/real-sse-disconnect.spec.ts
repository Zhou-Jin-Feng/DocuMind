import { expect, test, request as playwrightRequest } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const apiUrl = process.env.DOCUMIND_REAL_API;
if (!apiUrl) {
  throw new Error("DOCUMIND_REAL_API is required for the real SSE disconnect test.");
}

const evidenceDir =
  process.env.DOCUMIND_DISCONNECT_EVIDENCE_DIR ||
  "test-results/real-sse-disconnect";

test("server records client disconnect after the first SSE token", async ({ page }) => {
  test.setTimeout(240_000);
  fs.mkdirSync(evidenceDir, { recursive: true });
  const api = await playwrightRequest.newContext({ baseURL: apiUrl });
  const token = `R6-DISCONNECT-${Date.now()}`;
  const filename = `${token}.txt`;
  const content = [
    "隔离环境流式中断验证样例",
    "",
    `控制项 ${token} 的保留期为 37 天。`,
    `控制项 ${token} 仅用于服务端流关闭验证。`,
    "",
  ].join("\n");
  let documentKey: string | undefined;
  let streamRequestId: string | undefined;

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

    let active = false;
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const response = await api.get(`/api/v1/documents/${documentKey}`);
      const detail = (await response.json()) as { status?: string };
      if (detail.status === "active") {
        active = true;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 2_000));
    }
    expect(active).toBeTruthy();

    page.on("response", (response) => {
      if (response.url().includes("/api/v1/chat/stream")) {
        void response.allHeaders().then((headers) => {
          streamRequestId = headers["x-request-id"];
        });
      }
    });
    await page.goto("/");
    const streamResult = await page.evaluate(
      async ({ targetApiUrl, question }) => {
        const controller = new AbortController();
        const response = await fetch(`${targetApiUrl}/api/v1/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          throw new Error(`SSE request failed with HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          let separator = buffer.indexOf("\n\n");
          while (separator >= 0) {
            const frame = buffer.slice(0, separator);
            buffer = buffer.slice(separator + 2);
            const eventName = frame
              .split("\n")
              .find((line) => line.startsWith("event:"))
              ?.slice("event:".length)
              .trim();
            if (eventName === "token") {
              controller.abort();
              return { status: response.status, tokenObserved: true };
            }
            separator = buffer.indexOf("\n\n");
          }
        }
        return { status: response.status, tokenObserved: false };
      },
      {
        targetApiUrl: apiUrl,
        question: `控制项 ${token} 的保留期是多少天？`,
      },
    );

    expect(streamResult.status).toBe(200);
    expect(streamResult.tokenObserved).toBeTruthy();
    await expect.poll(() => streamRequestId).toBeTruthy();
    fs.writeFileSync(
      path.join(evidenceDir, "disconnect-evidence.json"),
      JSON.stringify(
        {
          filename,
          documentKey,
          requestId: streamRequestId,
          httpStatus: streamResult.status,
          tokenObservedBeforeAbort: streamResult.tokenObserved,
          clientAbortIssued: true,
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
