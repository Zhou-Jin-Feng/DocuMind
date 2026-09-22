import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const frontendUrl = "http://127.0.0.1:4273";
const apiUrl = "http://127.0.0.1:4274";
const storageKey = "rag-workbench-conversations-v1";
const runCount = 3;

interface FixtureMetadata {
  answerLength: number;
  answerSha256: string;
  chunkCount: number;
  chunkSize: number;
  chunkIntervalMs: number;
  historyMessageCount: number;
}

interface MetricSnapshot {
  startedAt: number;
  appRenderCount: number;
  reactCommitCount: number;
  messageRenderCounts: Record<string, number>;
  markdownRenderCounts: Record<string, number>;
  tokenMetrics: Array<{
    sequence: number;
    chars: number;
    receivedAt: number;
    visibleAt: number | null;
  }>;
  tokenBatchMetrics: Array<{
    sequence: number;
    chars: number;
    reason: "first" | "timer" | "terminal";
    dispatchedAt: number;
  }>;
  longTaskDurations: number[];
  frameDurations: number[];
}

interface ServerRunResponse {
  lastRun: {
    sentChunkCount: number;
    durationMs: number;
    sentAt: number[];
  } | null;
}

function percentile(values: number[], ratio: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))];
}

function summarize(values: number[]) {
  return {
    count: values.length,
    min: values.length ? Math.min(...values) : null,
    median: percentile(values, 0.5),
    p95: percentile(values, 0.95),
    max: values.length ? Math.max(...values) : null,
  };
}

function eventRatePerSecond(timestamps: number[]): number | null {
  if (timestamps.length < 2) return null;
  const durationMs = timestamps.at(-1)! - timestamps[0];
  return durationMs > 0 ? ((timestamps.length - 1) * 1000) / durationMs : null;
}

function createHistory() {
  const messages = Array.from({ length: 50 }, (_, index) => {
    const assistant = index % 2 === 1;
    return {
      id: `baseline-history-${String(index + 1).padStart(2, "0")}`,
      role: assistant ? "assistant" : "user",
      content: assistant
        ? `历史回答 ${index + 1}\n\n- 固定列表\n- 引用 [文档1]\n\n\`inline\``
        : `历史问题 ${index + 1}：如何验证流式回答？`,
      stage: "done",
      sources: assistant
        ? [
            {
              rank: 1,
              source: "history.txt",
              page_number: 1,
              excerpt: "固定历史来源。",
              distance: 0.2,
              chunk_id: `history-chunk-${index + 1}`,
            },
          ]
        : [],
    };
  });
  return [
    {
      id: "baseline-conversation",
      title: "FE-01 高频流式基线",
      messages,
      updatedAt: "2026-09-20T00:00:00.000Z",
    },
  ];
}

test("records the fixed high-frequency streaming profile", async ({
  browser,
  request,
}) => {
  const fixtureResponse = await request.get(`${apiUrl}/__fe01/fixture`);
  expect(fixtureResponse.ok()).toBeTruthy();
  const fixture = (await fixtureResponse.json()) as FixtureMetadata;
  expect(fixture).toMatchObject({
    answerLength: 10_000,
    chunkIntervalMs: 10,
    historyMessageCount: 50,
  });

  const runs = [];
  const browserVersion = browser.version();
  for (let run = 1; run <= runCount; run += 1) {
    const context = await browser.newContext({ baseURL: frontendUrl });
    await context.addInitScript(() => {
      const targetWindow = window as Window & {
        __DOCUMIND_FE01_REACT_COMMITS__?: number;
        __REACT_DEVTOOLS_GLOBAL_HOOK__?: unknown;
      };
      let nextRendererId = 0;
      const renderers = new Map<number, unknown>();
      targetWindow.__DOCUMIND_FE01_REACT_COMMITS__ = 0;
      targetWindow.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
        supportsFiber: true,
        renderers,
        inject(renderer: unknown) {
          nextRendererId += 1;
          renderers.set(nextRendererId, renderer);
          return nextRendererId;
        },
        onCommitFiberRoot() {
          targetWindow.__DOCUMIND_FE01_REACT_COMMITS__ =
            (targetWindow.__DOCUMIND_FE01_REACT_COMMITS__ ?? 0) + 1;
        },
        onCommitFiberUnmount() {},
      };
    });
    await context.addInitScript(
      ({ key, value }) => localStorage.setItem(key, value),
      { key: storageKey, value: JSON.stringify(createHistory()) },
    );
    const page = await context.newPage();
    await page.goto("/");
    await expect(page.getByText("服务就绪", { exact: true })).toBeVisible();
    await expect(page.locator(".message")).toHaveCount(50);
    await page.getByPlaceholder("向知识库提问").fill("运行 FE-01 固定性能样例");

    await page.evaluate(() => {
      const controller = window.__DOCUMIND_FE01_METRICS__;
      if (!controller) throw new Error("FE-01 metrics are not enabled");
      controller.reset();
    });
    const startedAt = await page.evaluate(() => performance.now());
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByRole("button", { name: "发送" })).toBeVisible({
      timeout: 60_000,
    });
    await expect
      .poll(() =>
        page.evaluate(
          ({ key }) => {
            const raw = localStorage.getItem(key);
            if (!raw) return 0;
            const conversations = JSON.parse(raw) as Array<{
              messages: Array<{ role: string; content: string }>;
            }>;
            const assistants = conversations[0]?.messages.filter(
              (message) => message.role === "assistant",
            );
            return assistants?.at(-1)?.content.length ?? 0;
          },
          { key: storageKey },
        ),
      )
      .toBe(fixture.answerLength);

    await page.evaluate(() => new Promise(requestAnimationFrame));
    const finishedAt = await page.evaluate(() => performance.now());
    const metrics = await page.evaluate(() => {
      const controller = window.__DOCUMIND_FE01_METRICS__;
      if (!controller) throw new Error("FE-01 metrics are not enabled");
      return controller.snapshot();
    }) as MetricSnapshot;
    const storedAnswer = await page.evaluate((key) => {
      const conversations = JSON.parse(localStorage.getItem(key) || "[]") as Array<{
        messages: Array<{ role: string; content: string }>;
      }>;
      return conversations[0].messages.filter((message) => message.role === "assistant").at(-1)
        ?.content ?? "";
    }, storageKey);
    expect(createHash("sha256").update(storedAnswer, "utf8").digest("hex")).toBe(
      fixture.answerSha256,
    );
    expect(metrics.tokenMetrics).toHaveLength(fixture.chunkCount);

    const serverRunResponse = await request.get(`${apiUrl}/__fe01/last-run`);
    expect(serverRunResponse.ok()).toBeTruthy();
    const serverRun = ((await serverRunResponse.json()) as ServerRunResponse)
      .lastRun;
    expect(serverRun?.sentChunkCount).toBe(fixture.chunkCount);
    const sendIntervals = (serverRun?.sentAt ?? [])
      .slice(1)
      .map((sentAt, index) => sentAt - (serverRun?.sentAt[index] ?? 0));

    const historyIds = Object.keys(metrics.markdownRenderCounts).filter((id) =>
      id.startsWith("baseline-history-"),
    );
    const historyMarkdownRenders = historyIds.reduce(
      (total, id) => total + metrics.markdownRenderCounts[id],
      0,
    );
    const visibleLatencies = metrics.tokenMetrics
      .filter((metric) => metric.visibleAt !== null)
      .map((metric) => (metric.visibleAt as number) - metric.receivedAt);
    const firstTokenMetric = metrics.tokenMetrics.find(
      (metric) => metric.sequence === 1,
    );
    const firstTokenVisibleLatencyMs =
      firstTokenMetric?.visibleAt === null || !firstTokenMetric
        ? null
        : firstTokenMetric.visibleAt - firstTokenMetric.receivedAt;
    const regularBatchTimes = metrics.tokenBatchMetrics
      .filter((metric) => metric.reason === "timer")
      .map((metric) => metric.dispatchedAt);
    const regularBatchIntervals = regularBatchTimes
      .slice(1)
      .map((timestamp, index) => timestamp - regularBatchTimes[index]);
    const regularTokenBatchRateHz = eventRatePerSecond(regularBatchTimes);
    const visibleLatencyMs = summarize(visibleLatencies);
    const batchReasons = metrics.tokenBatchMetrics.reduce(
      (counts, metric) => {
        counts[metric.reason] += 1;
        return counts;
      },
      { first: 0, timer: 0, terminal: 0 },
    );
    expect(
      metrics.tokenBatchMetrics.reduce((total, metric) => total + metric.chars, 0),
    ).toBe(fixture.answerLength);
    expect(batchReasons.first).toBe(1);
    expect(historyMarkdownRenders).toBe(0);
    expect(regularTokenBatchRateHz).not.toBeNull();
    expect(regularTokenBatchRateHz as number).toBeLessThanOrEqual(20);
    expect(visibleLatencyMs.p95).not.toBeNull();
    expect(visibleLatencyMs.p95 as number).toBeLessThanOrEqual(100);
    expect(visibleLatencyMs.max).not.toBeNull();
    expect(visibleLatencyMs.max as number).toBeLessThanOrEqual(100);
    expect(firstTokenVisibleLatencyMs).not.toBeNull();
    expect(firstTokenVisibleLatencyMs as number).toBeLessThanOrEqual(100);
    runs.push({
      run,
      durationMs: finishedAt - startedAt,
      appRenderCount: metrics.appRenderCount,
      reactCommitCount: metrics.reactCommitCount,
      historyMessageCount: fixture.historyMessageCount,
      historyMessagesRerendered: historyIds.length,
      historyMarkdownRenders,
      markdownRendersPerHistoryMessage:
        historyIds.length > 0 ? historyMarkdownRenders / historyIds.length : null,
      tokenEventCount: metrics.tokenMetrics.length,
      tokenBatchCount: metrics.tokenBatchMetrics.length,
      tokenBatchReasons: batchReasons,
      regularTokenBatchRateHz,
      regularTokenBatchIntervalMs: summarize(regularBatchIntervals),
      firstTokenVisibleLatencyMs,
      serverStreamDurationMs: serverRun?.durationMs ?? null,
      serverSendIntervalMs: summarize(sendIntervals),
      visibleLatencyMs,
      longTasksMs: summarize(metrics.longTaskDurations),
      frameDurationMs: summarize(metrics.frameDurations),
      framesOver50Ms: metrics.frameDurations.filter((duration) => duration > 50).length,
    });
    await context.close();
  }

  const lock = JSON.parse(
    readFileSync(path.resolve(process.cwd(), "package-lock.json"), "utf8"),
  ) as {
    packages: Record<string, { version?: string }>;
  };
  const report = {
    schemaVersion: 2,
    measuredAt: new Date().toISOString(),
    environment: {
      build: "Vite production build with streaming counters enabled",
      reactStrictMode: "present; development-only double invocation is inactive",
      node: process.version,
      chromium: browserVersion,
      react: lock.packages["node_modules/react"]?.version ?? "unknown",
      reactDom: lock.packages["node_modules/react-dom"]?.version ?? "unknown",
      reactMarkdown:
        lock.packages["node_modules/react-markdown"]?.version ?? "unknown",
      viewport: "1280x720",
    },
    fixture,
    runs,
    aggregate: {
      durationMs: summarize(runs.map((run) => run.durationMs)),
      reactCommitCount: summarize(runs.map((run) => run.reactCommitCount)),
      tokenBatchCount: summarize(runs.map((run) => run.tokenBatchCount)),
      regularTokenBatchRateHz: summarize(
        runs.map((run) => run.regularTokenBatchRateHz ?? 0),
      ),
      historyMarkdownRenders: summarize(
        runs.map((run) => run.historyMarkdownRenders),
      ),
      serverSendIntervalMedianMs: summarize(
        runs.map((run) => run.serverSendIntervalMs.median ?? 0),
      ),
      visibleLatencyMedianMs: summarize(
        runs.map((run) => run.visibleLatencyMs.median ?? 0),
      ),
      firstTokenVisibleLatencyMs: summarize(
        runs.map((run) => run.firstTokenVisibleLatencyMs ?? 0),
      ),
      visibleLatencyP95Ms: summarize(
        runs.map((run) => run.visibleLatencyMs.p95 ?? 0),
      ),
      longTaskCount: summarize(runs.map((run) => run.longTasksMs.count)),
      longTaskMaxMs: summarize(runs.map((run) => run.longTasksMs.max ?? 0)),
      frameDurationMedianMs: summarize(
        runs.map((run) => run.frameDurationMs.median ?? 0),
      ),
      frameDurationMaxMs: summarize(
        runs.map((run) => run.frameDurationMs.max ?? 0),
      ),
      framesOver50Ms: summarize(runs.map((run) => run.framesOver50Ms)),
    },
    limitations: [
      "Synthetic local Mock results do not predict real provider or user-device performance.",
      "Markdown render counters execute inside MessageItem; memoized historical items produce no new counter entries after reset.",
      "Visible latency runs from token callback receipt to the next message-list DOM mutation.",
      "Token batches distinguish the immediate first append, timer-driven regular appends, and terminal flushes.",
      "The Mock timer target is fixed at 10 ms; actual send intervals are measured separately.",
    ],
  };
  const configuredOutput = process.env.DOCUMIND_STREAMING_REPORT_PATH?.trim();
  if (!configuredOutput) {
    throw new Error(
      "DOCUMIND_STREAMING_REPORT_PATH must be set by the FE-01 or FE-03 Playwright config; refusing to overwrite a baseline.",
    );
  }
  const outputPath = path.resolve(process.cwd(), configuredOutput);
  const writeMode = process.env.DOCUMIND_STREAMING_WRITE_MODE?.trim() || "replace";
  if (writeMode === "create-only" && existsSync(outputPath)) {
    throw new Error(
      `Refusing to overwrite frozen streaming measurement archive: ${outputPath}`,
    );
  }
  const outputDirectory = path.dirname(outputPath);
  mkdirSync(outputDirectory, { recursive: true });
  writeFileSync(
    outputPath,
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );
});
