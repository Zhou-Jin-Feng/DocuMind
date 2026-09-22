import type { ChatMessage } from "./types";
import type { ChatTokenBatchReason } from "./features/chat/streamController";

export interface Fe01TokenMetric {
  sequence: number;
  chars: number;
  receivedAt: number;
  visibleAt: number | null;
}

export interface Fe01TokenBatchMetric {
  sequence: number;
  chars: number;
  reason: ChatTokenBatchReason;
  dispatchedAt: number;
}

export interface Fe01MetricsSnapshot {
  startedAt: number;
  appRenderCount: number;
  reactCommitCount: number;
  messageRenderCounts: Record<string, number>;
  markdownRenderCounts: Record<string, number>;
  tokenMetrics: Fe01TokenMetric[];
  tokenBatchMetrics: Fe01TokenBatchMetric[];
  longTaskDurations: number[];
  frameDurations: number[];
}

interface Fe01MetricsController {
  reset: () => void;
  snapshot: () => Fe01MetricsSnapshot;
}

declare global {
  interface Window {
    __DOCUMIND_FE01_METRICS__?: Fe01MetricsController;
    __DOCUMIND_FE01_REACT_COMMITS__?: number;
  }
}

const enabled = import.meta.env.VITE_FE01_PROFILE === "1";

let currentSnapshot: Fe01MetricsSnapshot | null = null;
let pendingTokens: Fe01TokenMetric[] = [];
let mutationObserver: MutationObserver | null = null;
let longTaskObserver: PerformanceObserver | null = null;
let frameRequest: number | null = null;
let lastFrameAt: number | null = null;

function createSnapshot(): Fe01MetricsSnapshot {
  return {
    startedAt: performance.now(),
    appRenderCount: 0,
    reactCommitCount: 0,
    messageRenderCounts: {},
    markdownRenderCounts: {},
    tokenMetrics: [],
    tokenBatchMetrics: [],
    longTaskDurations: [],
    frameDurations: [],
  };
}

function getSnapshot(): Fe01MetricsSnapshot {
  currentSnapshot ??= createSnapshot();
  return currentSnapshot;
}

function cloneSnapshot(): Fe01MetricsSnapshot {
  const snapshot = getSnapshot();
  return {
    ...snapshot,
    reactCommitCount: window.__DOCUMIND_FE01_REACT_COMMITS__ ?? 0,
    messageRenderCounts: { ...snapshot.messageRenderCounts },
    markdownRenderCounts: { ...snapshot.markdownRenderCounts },
    tokenMetrics: snapshot.tokenMetrics.map((metric) => ({ ...metric })),
    tokenBatchMetrics: snapshot.tokenBatchMetrics.map((metric) => ({ ...metric })),
    longTaskDurations: [...snapshot.longTaskDurations],
    frameDurations: [...snapshot.frameDurations],
  };
}

function observeMessageList(): void {
  const messageList = document.querySelector(".message-list");
  if (!messageList) return;
  mutationObserver?.disconnect();
  mutationObserver = new MutationObserver(() => {
    if (pendingTokens.length === 0) return;
    const visibleAt = performance.now();
    for (const metric of pendingTokens) {
      metric.visibleAt = visibleAt;
    }
    pendingTokens = [];
  });
  mutationObserver.observe(messageList, {
    characterData: true,
    childList: true,
    subtree: true,
  });
}

function observeLongTasks(): void {
  longTaskObserver?.disconnect();
  if (!("PerformanceObserver" in window)) return;
  try {
    longTaskObserver = new PerformanceObserver((list) => {
      const snapshot = getSnapshot();
      for (const entry of list.getEntries()) {
        snapshot.longTaskDurations.push(entry.duration);
      }
    });
    longTaskObserver.observe({ type: "longtask", buffered: false });
  } catch {
    longTaskObserver = null;
  }
}

function observeFrames(): void {
  if (frameRequest !== null) return;
  const onFrame = (timestamp: number) => {
    const snapshot = getSnapshot();
    if (lastFrameAt !== null) {
      snapshot.frameDurations.push(timestamp - lastFrameAt);
    }
    lastFrameAt = timestamp;
    frameRequest = requestAnimationFrame(onFrame);
  };
  frameRequest = requestAnimationFrame(onFrame);
}

function reset(): void {
  currentSnapshot = createSnapshot();
  window.__DOCUMIND_FE01_REACT_COMMITS__ = 0;
  pendingTokens = [];
  lastFrameAt = null;
  observeMessageList();
  observeLongTasks();
  observeFrames();
}

if (enabled) {
  window.__DOCUMIND_FE01_METRICS__ = {
    reset,
    snapshot: cloneSnapshot,
  };
}

export function recordFe01AppRender(): void {
  if (enabled) getSnapshot().appRenderCount += 1;
}

export function recordFe01MessageRender(message: ChatMessage): void {
  if (!enabled) return;
  const snapshot = getSnapshot();
  snapshot.messageRenderCounts[message.id] =
    (snapshot.messageRenderCounts[message.id] ?? 0) + 1;
  if (message.content) {
    snapshot.markdownRenderCounts[message.id] =
      (snapshot.markdownRenderCounts[message.id] ?? 0) + 1;
  }
}

export function recordFe01TokenReceived(chars: number): void {
  if (!enabled) return;
  const snapshot = getSnapshot();
  const metric: Fe01TokenMetric = {
    sequence: snapshot.tokenMetrics.length + 1,
    chars,
    receivedAt: performance.now(),
    visibleAt: null,
  };
  snapshot.tokenMetrics.push(metric);
  pendingTokens.push(metric);
}

export function recordFe01TokenBatch(
  chars: number,
  reason: ChatTokenBatchReason,
): void {
  if (!enabled) return;
  const snapshot = getSnapshot();
  snapshot.tokenBatchMetrics.push({
    sequence: snapshot.tokenBatchMetrics.length + 1,
    chars,
    reason,
    dispatchedAt: performance.now(),
  });
}
