import { chromium } from "@playwright/test";
import { expect, test } from "vitest";
import { createServer, type Plugin } from "vite";

interface MetricsSnapshot {
  messageRenderCounts: Record<string, number>;
  markdownRenderCounts: Record<string, number>;
}

const harnessEntry = "\0virtual:message-list-render-harness.js";

function messageListHarness(): Plugin {
  return {
    name: "message-list-render-harness",
    enforce: "pre",
    configureServer(server) {
      server.middlewares.use("/__message-list_render_test__", (_request, response) => {
        response.statusCode = 200;
        response.setHeader("Content-Type", "text/html; charset=utf-8");
        response.end(`
          <!doctype html>
          <html lang="zh-CN">
            <body>
              <div id="root"></div>
              <script type="module" src="/__message-list_render_harness__.js"></script>
            </body>
          </html>
        `);
      });
    },
    resolveId(id) {
      if (id === "/__message-list_render_harness__.js") return harnessEntry;
    },
    load(id) {
      if (id !== harnessEntry) return;
      return `
        import { createElement, createRef } from "react";
        import { createRoot } from "react-dom/client";
        import { MessageList } from "/src/components/MessageList.tsx";

        const historicalQuestion = {
          id: "history-question",
          role: "user",
          content: "历史 *问题*",
          stage: "done",
          sources: [],
        };
        const historicalAnswer = {
          id: "history-answer",
          role: "assistant",
          content: "历史 **回答**",
          stage: "done",
          sources: [],
        };
        let currentAnswer = {
          id: "current-answer",
          role: "assistant",
          content: "流式 **初始**",
          stage: "generating",
          sources: [],
        };
        const onOpenSources = () => {};
        const onPromptSelect = () => {};
        const root = createRoot(document.getElementById("root"));

        function render() {
          root.render(createElement(MessageList, {
            messages: [historicalQuestion, historicalAnswer, currentAnswer],
            documentCount: 1,
            conversationId: "harness-conversation",
            onOpenSources,
            onPromptSelect,
          }));
        }

        window.__updateCurrentAnswer = (content) => {
          currentAnswer = { ...currentAnswer, content };
          render();
        };

        render();
      `;
    },
  };
}

test(
  "does not re-render unchanged historical Markdown when the current answer changes",
  async () => {
    const server = await createServer({
      configFile: false,
      root: ".",
      logLevel: "error",
      define: {
        "import.meta.env.VITE_FE01_PROFILE": JSON.stringify("1"),
      },
      plugins: [messageListHarness()],
      server: { host: "127.0.0.1", port: 0 },
    });
    let browser: Awaited<ReturnType<typeof chromium.launch>> | null = null;

    try {
      browser = await chromium.launch({ headless: true });
      await server.listen();
      const origin = server.resolvedUrls?.local[0];
      if (!origin) throw new Error("Vite did not expose a local test URL.");

      const page = await browser.newPage();
      const pageErrors: string[] = [];
      page.on("pageerror", (error) => pageErrors.push(error.message));
      await page.goto(new URL("/__message-list_render_test__", origin).href, {
        timeout: 15_000,
      });
      try {
        await page.locator(".message").nth(2).waitFor({ timeout: 15_000 });
      } catch (error) {
        throw new Error(
          `MessageList harness did not mount: ${pageErrors.join(" | ") || String(error)}`,
        );
      }
      await page.evaluate(() => {
        const metrics = window.__DOCUMIND_FE01_METRICS__;
        if (!metrics) throw new Error("FE-01 render metrics are not enabled.");
        metrics.reset();
      });

      await page.evaluate(() => {
        const testWindow = window as Window & {
          __updateCurrentAnswer?: (content: string) => void;
        };
        if (!testWindow.__updateCurrentAnswer) {
          throw new Error("MessageList render harness is not ready.");
        }
        testWindow.__updateCurrentAnswer("流式 **更新**");
      });
      const renderedStrong = await page
        .locator(".message")
        .nth(2)
        .locator("strong")
        .textContent();
      const metrics = await page.evaluate(() => {
        const controller = window.__DOCUMIND_FE01_METRICS__;
        if (!controller) throw new Error("FE-01 render metrics are not enabled.");
        return controller.snapshot();
      }) as MetricsSnapshot;

      expect({
        renderedStrong,
        historyQuestionRenders: metrics.markdownRenderCounts["history-question"] ?? 0,
        historyAnswerRenders: metrics.markdownRenderCounts["history-answer"] ?? 0,
        currentAnswerRenders: metrics.markdownRenderCounts["current-answer"] ?? 0,
      }).toEqual({
        renderedStrong: "更新",
        historyQuestionRenders: 0,
        historyAnswerRenders: 0,
        currentAnswerRenders: 1,
      });
    } finally {
      await browser?.close();
      await server.close();
    }
  },
  30_000,
);
