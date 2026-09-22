import { APIError } from "../../api";
import type { ChatEvent } from "../../types";
import type { AnswerTarget, AnswerUpdate } from "./conversationState";

const COMPLETE_FALLBACK = "回答生成完成。";
const STOP_FALLBACK = "生成已停止。";
const NETWORK_ERROR_MESSAGE = "无法连接问答服务。";
const UNEXPECTED_EOF_MESSAGE = "问答流意外结束，请重试。";
const DEFAULT_FLUSH_INTERVAL_MS = 50;

type TimerHandle = ReturnType<typeof globalThis.setTimeout>;

export interface ChatRunIdentity extends AnswerTarget {
  requestId: string;
}

export type ChatTokenBatchReason = "first" | "timer" | "terminal";

export type ChatTransport = (
  question: string,
  callbacks: { onEvent: (event: ChatEvent) => void },
  signal: AbortSignal,
) => Promise<void>;

export interface TimerScheduler {
  setTimeout(callback: () => void, delayMs: number): TimerHandle;
  clearTimeout(handle: TimerHandle): void;
}

export interface ChatStreamControllerOptions {
  transport: ChatTransport;
  onUpdate(target: AnswerTarget, update: AnswerUpdate): void;
  onActiveChange(identity: ChatRunIdentity | null): void;
  onTokenReceived?(chars: number): void;
  onTokenBatch?(chars: number, reason: ChatTokenBatchReason): void;
  scheduler?: TimerScheduler;
  flushIntervalMs?: number;
}

export interface ChatStreamController {
  start(input: { identity: ChatRunIdentity; question: string }): void;
  stop(): void;
  dispose(): void;
}

interface ActiveRun {
  identity: ChatRunIdentity;
  target: AnswerTarget;
  abortController: AbortController;
  settled: boolean;
  hasDisplayedToken: boolean;
  pendingText: string;
  flushTimer: TimerHandle | null;
  timerGeneration: number;
}

export function createChatStreamController(
  options: ChatStreamControllerOptions,
): ChatStreamController {
  let activeRun: ActiveRun | null = null;
  let disposed = false;
  let startGeneration = 0;
  const scheduler: TimerScheduler = options.scheduler ?? {
    setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
    clearTimeout: (handle) => globalThis.clearTimeout(handle),
  };
  const flushIntervalMs =
    options.flushIntervalMs !== undefined &&
    Number.isFinite(options.flushIntervalMs) &&
    options.flushIntervalMs >= 0
      ? options.flushIntervalMs
      : DEFAULT_FLUSH_INTERVAL_MS;

  function isCurrent(run: ActiveRun): boolean {
    return (
      !disposed &&
      !run.settled &&
      activeRun === run &&
      activeRun.identity.requestId === run.identity.requestId
    );
  }

  function cancelFlushTimer(run: ActiveRun): void {
    run.timerGeneration += 1;
    if (run.flushTimer === null) return;
    scheduler.clearTimeout(run.flushTimer);
    run.flushTimer = null;
  }

  function dispatchAppend(
    run: ActiveRun,
    text: string,
    reason: ChatTokenBatchReason,
  ): void {
    if (!isCurrent(run) || !text) return;
    options.onTokenBatch?.(text.length, reason);
    if (!isCurrent(run)) return;
    options.onUpdate(run.target, { kind: "append", text });
  }

  function flushPending(
    run: ActiveRun,
    reason: Extract<ChatTokenBatchReason, "timer" | "terminal">,
  ): void {
    if (!isCurrent(run) || !run.pendingText) return;
    const text = run.pendingText;
    run.pendingText = "";
    dispatchAppend(run, text, reason);
  }

  function scheduleFlush(run: ActiveRun): void {
    if (!isCurrent(run) || run.flushTimer !== null) return;
    const generation = run.timerGeneration + 1;
    run.timerGeneration = generation;
    run.flushTimer = scheduler.setTimeout(() => {
      if (run.timerGeneration !== generation) return;
      run.flushTimer = null;
      flushPending(run, "timer");
    }, flushIntervalMs);
  }

  function settle(
    run: ActiveRun,
    update: AnswerUpdate,
    abortTransport = false,
  ): void {
    if (!isCurrent(run)) return;

    cancelFlushTimer(run);
    flushPending(run, "terminal");
    if (!isCurrent(run)) return;

    run.settled = true;
    options.onUpdate(run.target, update);

    if (activeRun === run) {
      activeRun = null;
      options.onActiveChange(null);
    }

    if (abortTransport && !run.abortController.signal.aborted) {
      run.abortController.abort();
    }
  }

  function stopRun(run: ActiveRun): void {
    settle(run, { kind: "stop", fallback: STOP_FALLBACK }, true);
  }

  function handleEvent(run: ActiveRun, event: ChatEvent): void {
    if (!isCurrent(run)) return;

    if (event.type === "status") {
      options.onUpdate(run.target, {
        kind: "status",
        stage: event.data.stage,
      });
      return;
    }

    if (event.type === "sources") {
      options.onUpdate(run.target, {
        kind: "sources",
        items: event.data.items,
      });
      return;
    }

    if (event.type === "token") {
      const text = event.data.text;
      if (!text) return;
      options.onTokenReceived?.(text.length);
      if (!isCurrent(run)) return;

      if (!run.hasDisplayedToken) {
        run.hasDisplayedToken = true;
        dispatchAppend(run, text, "first");
        return;
      }

      run.pendingText += text;
      scheduleFlush(run);
      return;
    }

    if (event.type === "done") {
      settle(run, {
        kind: "complete",
        fallback: event.data.message || COMPLETE_FALLBACK,
      });
      return;
    }

    settle(run, { kind: "fail", message: event.data.message });
  }

  function handleTransportFailure(run: ActiveRun, error: unknown): void {
    if (!isCurrent(run)) return;
    settle(run, {
      kind: "fail",
      message: error instanceof APIError ? error.message : NETWORK_ERROR_MESSAGE,
    });
  }

  function handleTransportCompletion(run: ActiveRun): void {
    if (!isCurrent(run)) return;
    settle(run, { kind: "fail", message: UNEXPECTED_EOF_MESSAGE });
  }

  return {
    start({ identity: inputIdentity, question }): void {
      if (disposed) return;
      const generation = startGeneration + 1;
      startGeneration = generation;

      if (activeRun) {
        stopRun(activeRun);
      }
      if (disposed || generation !== startGeneration) return;

      const identity: ChatRunIdentity = { ...inputIdentity };
      const run: ActiveRun = {
        identity,
        target: {
          conversationId: identity.conversationId,
          answerId: identity.answerId,
        },
        abortController: new AbortController(),
        settled: false,
        hasDisplayedToken: false,
        pendingText: "",
        flushTimer: null,
        timerGeneration: 0,
      };

      activeRun = run;
      options.onActiveChange(identity);
      if (!isCurrent(run)) return;

      let transportResult: Promise<void>;
      try {
        transportResult = options.transport(
          question,
          { onEvent: (event) => handleEvent(run, event) },
          run.abortController.signal,
        );
      } catch (error) {
        handleTransportFailure(run, error);
        return;
      }

      void transportResult.then(
        () => handleTransportCompletion(run),
        (error: unknown) => handleTransportFailure(run, error),
      );
    },

    stop(): void {
      if (!activeRun || disposed) return;
      stopRun(activeRun);
    },

    dispose(): void {
      if (disposed) return;
      disposed = true;

      const run = activeRun;
      activeRun = null;
      if (!run) return;

      cancelFlushTimer(run);
      run.pendingText = "";
      run.settled = true;
      if (!run.abortController.signal.aborted) {
        run.abortController.abort();
      }
    },
  };
}
