import { describe, expect, it } from "vitest";
import { APIError } from "../../api";
import type { ChatEvent, SourceReference } from "../../types";
import type { AnswerTarget, AnswerUpdate } from "./conversationState";
import {
  createChatStreamController,
  type ChatRunIdentity,
  type ChatStreamController,
  type ChatTransport,
  type TimerScheduler,
} from "./streamController";

interface DeferredRun {
  question: string;
  signal: AbortSignal;
  emit(event: ChatEvent): void;
  resolve(): void;
  reject(error: unknown): void;
}

function createDeferredTransport(): {
  transport: ChatTransport;
  runs: DeferredRun[];
} {
  const runs: DeferredRun[] = [];
  const transport: ChatTransport = (question, callbacks, signal) => {
    let resolve!: () => void;
    let reject!: (error: unknown) => void;
    const result = new Promise<void>((resolvePromise, rejectPromise) => {
      resolve = resolvePromise;
      reject = rejectPromise;
    });

    runs.push({
      question,
      signal,
      emit: callbacks.onEvent,
      resolve,
      reject,
    });
    return result;
  };

  return { transport, runs };
}

function identity(requestId: string, answerId = `answer-${requestId}`): ChatRunIdentity {
  return {
    requestId,
    conversationId: `conversation-${requestId}`,
    answerId,
  };
}

async function runPromiseHandlers(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

interface ScheduledTask {
  id: number;
  dueAt: number;
  callback: () => void;
  cleared: boolean;
  ran: boolean;
}

class FakeScheduler implements TimerScheduler {
  private now = 0;
  private nextId = 1;
  private readonly tasks = new Map<number, ScheduledTask>();
  scheduledCount = 0;
  clearedCount = 0;

  setTimeout(
    callback: () => void,
    delayMs: number,
  ): ReturnType<typeof globalThis.setTimeout> {
    const task: ScheduledTask = {
      id: this.nextId,
      dueAt: this.now + delayMs,
      callback,
      cleared: false,
      ran: false,
    };
    this.nextId += 1;
    this.scheduledCount += 1;
    this.tasks.set(task.id, task);
    return task.id as ReturnType<typeof globalThis.setTimeout>;
  }

  clearTimeout(handle: ReturnType<typeof globalThis.setTimeout>): void {
    const task = this.tasks.get(handle as number);
    if (!task || task.cleared || task.ran) return;
    task.cleared = true;
    this.clearedCount += 1;
  }

  advanceBy(milliseconds: number): void {
    const targetTime = this.now + milliseconds;
    while (true) {
      const task = [...this.tasks.values()]
        .filter((candidate) =>
          !candidate.cleared && !candidate.ran && candidate.dueAt <= targetTime
        )
        .sort((left, right) => left.dueAt - right.dueAt || left.id - right.id)[0];
      if (!task) break;
      this.now = task.dueAt;
      task.ran = true;
      task.callback();
    }
    this.now = targetTime;
  }

  pendingCount(): number {
    return [...this.tasks.values()].filter((task) => !task.cleared && !task.ran)
      .length;
  }

  latestHandle(): ReturnType<typeof globalThis.setTimeout> {
    if (this.nextId === 1) throw new Error("No timer has been scheduled");
    return (this.nextId - 1) as ReturnType<typeof globalThis.setTimeout>;
  }

  fireEvenIfCleared(handle: ReturnType<typeof globalThis.setTimeout>): void {
    const task = this.tasks.get(handle as number);
    if (!task || task.ran) return;
    task.ran = true;
    task.callback();
  }
}

function createHarness() {
  const deferred = createDeferredTransport();
  const updates: Array<{ target: AnswerTarget; update: AnswerUpdate }> = [];
  const activeChanges: Array<ChatRunIdentity | null> = [];
  const sequence: string[] = [];
  const scheduler = new FakeScheduler();
  const controller = createChatStreamController({
    transport: deferred.transport,
    onUpdate: (target, update) => {
      updates.push({ target, update });
      sequence.push(`update:${update.kind}`);
    },
    onActiveChange: (activeIdentity) => {
      activeChanges.push(activeIdentity);
      sequence.push(activeIdentity ? `active:${activeIdentity.requestId}` : "active:null");
    },
    scheduler,
    flushIntervalMs: 50,
  });

  return {
    ...deferred,
    controller,
    updates,
    activeChanges,
    sequence,
    scheduler,
  };
}

type Harness = ReturnType<typeof createHarness>;

interface PendingTerminalCase {
  label: string;
  trigger(harness: Harness): Promise<void>;
  expectedTerminal: AnswerUpdate;
  abortsTransport?: boolean;
}

const pendingTerminalCases: PendingTerminalCase[] = [
  {
    label: "done",
    trigger: async (harness) => {
      harness.runs[0].emit({ type: "done", data: { status: "success" } });
    },
    expectedTerminal: { kind: "complete", fallback: "回答生成完成。" },
  },
  {
    label: "SSE error",
    trigger: async (harness) => {
      harness.runs[0].emit({
        type: "error",
        data: {
          code: "provider_failed",
          message: "Provider unavailable.",
          partial: true,
          retryable: true,
        },
      });
    },
    expectedTerminal: { kind: "fail", message: "Provider unavailable." },
  },
  {
    label: "network rejection",
    trigger: async (harness) => {
      harness.runs[0].reject(new TypeError("fetch failed"));
      await runPromiseHandlers();
    },
    expectedTerminal: { kind: "fail", message: "无法连接问答服务。" },
  },
  {
    label: "unexpected EOF",
    trigger: async (harness) => {
      harness.runs[0].resolve();
      await runPromiseHandlers();
    },
    expectedTerminal: { kind: "fail", message: "问答流意外结束，请重试。" },
  },
  {
    label: "manual stop",
    trigger: async (harness) => {
      harness.controller.stop();
    },
    expectedTerminal: { kind: "stop", fallback: "生成已停止。" },
    abortsTransport: true,
  },
];

describe("chat stream controller", () => {
  it("shows the first non-empty token immediately and batches later tokens every 50ms", async () => {
    const harness = createHarness();
    const runIdentity = identity("request-a");
    const source: SourceReference = {
      rank: 1,
      source: "guide.txt",
      excerpt: "RAG combines retrieval and generation.",
    };

    harness.controller.start({ identity: runIdentity, question: "What is RAG?" });
    expect(harness.runs).toHaveLength(1);
    expect(harness.runs[0].question).toBe("What is RAG?");
    expect(harness.activeChanges).toEqual([runIdentity]);

    harness.runs[0].emit({ type: "status", data: { stage: "generating" } });
    harness.runs[0].emit({ type: "sources", data: { items: [source] } });
    harness.runs[0].emit({ type: "token", data: { text: "" } });
    harness.runs[0].emit({ type: "token", data: { text: "first" } });
    harness.runs[0].emit({ type: "token", data: { text: " second" } });
    harness.runs[0].emit({ type: "token", data: { text: " third" } });

    expect(harness.updates).toEqual([
      {
        target: { conversationId: "conversation-request-a", answerId: "answer-request-a" },
        update: { kind: "status", stage: "generating" },
      },
      {
        target: { conversationId: "conversation-request-a", answerId: "answer-request-a" },
        update: { kind: "sources", items: [source] },
      },
      {
        target: { conversationId: "conversation-request-a", answerId: "answer-request-a" },
        update: { kind: "append", text: "first" },
      },
    ]);
    expect(harness.scheduler.scheduledCount).toBe(1);
    expect(harness.scheduler.pendingCount()).toBe(1);

    harness.scheduler.advanceBy(49);
    expect(harness.updates).toHaveLength(3);
    harness.scheduler.advanceBy(1);
    expect(harness.updates.at(-1)).toEqual({
      target: { conversationId: "conversation-request-a", answerId: "answer-request-a" },
      update: { kind: "append", text: " second third" },
    });
    expect(harness.scheduler.pendingCount()).toBe(0);

    harness.runs[0].emit({ type: "token", data: { text: " fourth" } });
    expect(harness.scheduler.scheduledCount).toBe(2);
    expect(harness.updates.at(-1)?.update).not.toEqual({
      kind: "append",
      text: " fourth",
    });
    harness.scheduler.advanceBy(50);
    expect(harness.updates.at(-1)).toEqual({
      target: { conversationId: "conversation-request-a", answerId: "answer-request-a" },
      update: { kind: "append", text: " fourth" },
    });

    harness.runs[0].emit({
      type: "done",
      data: { status: "success", message: "Completed without tokens." },
    });
    expect(harness.updates.at(-1)).toEqual({
      target: { conversationId: "conversation-request-a", answerId: "answer-request-a" },
      update: { kind: "complete", fallback: "Completed without tokens." },
    });
    expect(harness.activeChanges).toEqual([runIdentity, null]);

    const updateCount = harness.updates.length;
    harness.runs[0].emit({ type: "token", data: { text: "late" } });
    harness.runs[0].resolve();
    await runPromiseHandlers();
    expect(harness.updates).toHaveLength(updateCount);
    expect(harness.activeChanges).toEqual([runIdentity, null]);
  });

  it.each(pendingTerminalCases)(
    "flushes pending text before $label settles the run",
    async ({ label, trigger, expectedTerminal, abortsTransport }) => {
      const harness = createHarness();
      const runIdentity = identity(`terminal-${label}`);
      const target = {
        conversationId: runIdentity.conversationId,
        answerId: runIdentity.answerId,
      };
      harness.controller.start({ identity: runIdentity, question: label });
      harness.runs[0].signal.addEventListener("abort", () => {
        harness.sequence.push("abort");
      });
      harness.runs[0].emit({ type: "token", data: { text: "visible" } });
      harness.runs[0].emit({ type: "token", data: { text: " pending" } });
      harness.sequence.push(`trigger:${label}`);

      await trigger(harness);

      expect(harness.updates).toEqual([
        { target, update: { kind: "append", text: "visible" } },
        { target, update: { kind: "append", text: " pending" } },
        { target, update: expectedTerminal },
      ]);
      expect(harness.sequence).toEqual([
        `active:${runIdentity.requestId}`,
        "update:append",
        `trigger:${label}`,
        "update:append",
        `update:${expectedTerminal.kind}`,
        "active:null",
        ...(abortsTransport ? ["abort"] : []),
      ]);
      expect(harness.scheduler.clearedCount).toBe(1);
      expect(harness.scheduler.pendingCount()).toBe(0);
      expect(harness.activeChanges).toEqual([runIdentity, null]);
    },
  );

  it("drops pending text and clears its timer when disposed", async () => {
    const harness = createHarness();
    const runIdentity = identity("request-dispose-pending");
    harness.controller.start({ identity: runIdentity, question: "Dispose pending" });
    harness.runs[0].emit({ type: "token", data: { text: "visible" } });
    harness.runs[0].emit({ type: "token", data: { text: " discarded" } });
    const staleHandle = harness.scheduler.latestHandle();

    expect(harness.updates).toEqual([
      {
        target: {
          conversationId: "conversation-request-dispose-pending",
          answerId: "answer-request-dispose-pending",
        },
        update: { kind: "append", text: "visible" },
      },
    ]);
    expect(harness.scheduler.pendingCount()).toBe(1);

    harness.controller.dispose();
    expect(harness.runs[0].signal.aborted).toBe(true);
    expect(harness.scheduler.clearedCount).toBe(1);
    expect(harness.scheduler.pendingCount()).toBe(0);

    harness.scheduler.fireEvenIfCleared(staleHandle);
    harness.runs[0].emit({ type: "token", data: { text: " late" } });
    harness.runs[0].reject(new APIError("late failure", "late_failure"));
    await runPromiseHandlers();

    expect(harness.updates).toHaveLength(1);
    expect(harness.activeChanges).toEqual([runIdentity]);
  });

  it("ignores a stale timer, event, and rejection after a new request starts", async () => {
    const harness = createHarness();
    const identityA = identity("request-timer-a", "answer-a");
    const identityB = identity("request-timer-b", "answer-b");
    harness.controller.start({ identity: identityA, question: "A" });
    harness.runs[0].emit({ type: "token", data: { text: "A visible" } });
    harness.runs[0].emit({ type: "token", data: { text: " A pending" } });
    const staleHandle = harness.scheduler.latestHandle();

    harness.controller.start({ identity: identityB, question: "B" });
    harness.runs[1].emit({ type: "token", data: { text: "B visible" } });
    harness.runs[1].emit({ type: "token", data: { text: " B pending" } });
    expect(harness.updates).toEqual([
      {
        target: { conversationId: "conversation-request-timer-a", answerId: "answer-a" },
        update: { kind: "append", text: "A visible" },
      },
      {
        target: { conversationId: "conversation-request-timer-a", answerId: "answer-a" },
        update: { kind: "append", text: " A pending" },
      },
      {
        target: { conversationId: "conversation-request-timer-a", answerId: "answer-a" },
        update: { kind: "stop", fallback: "生成已停止。" },
      },
      {
        target: { conversationId: "conversation-request-timer-b", answerId: "answer-b" },
        update: { kind: "append", text: "B visible" },
      },
    ]);
    expect(harness.activeChanges).toEqual([identityA, null, identityB]);
    expect(harness.runs[0].signal.aborted).toBe(true);

    const updateCount = harness.updates.length;
    harness.scheduler.fireEvenIfCleared(staleHandle);
    harness.runs[0].emit({ type: "token", data: { text: " late A" } });
    harness.runs[0].reject(new APIError("late A failure", "late_a"));
    await runPromiseHandlers();
    expect(harness.updates).toHaveLength(updateCount);
    expect(harness.activeChanges).toEqual([identityA, null, identityB]);

    harness.scheduler.advanceBy(50);
    expect(harness.updates.at(-1)).toEqual({
      target: { conversationId: "conversation-request-timer-b", answerId: "answer-b" },
      update: { kind: "append", text: " B pending" },
    });
    harness.runs[1].emit({ type: "done", data: { status: "success" } });
    expect(harness.activeChanges).toEqual([identityA, null, identityB, null]);
  });

  it("does not overwrite a request started reentrantly while replacing the active run", () => {
    const deferred = createDeferredTransport();
    const identityA = identity("request-reentrant-a", "answer-a");
    const identityB = identity("request-reentrant-b", "answer-b");
    const identityC = identity("request-reentrant-c", "answer-c");
    const activeChanges: Array<ChatRunIdentity | null> = [];
    let startedC = false;
    let controller!: ChatStreamController;

    controller = createChatStreamController({
      transport: deferred.transport,
      onUpdate: (target, update) => {
        if (
          !startedC &&
          target.answerId === identityA.answerId &&
          update.kind === "stop"
        ) {
          startedC = true;
          controller.start({ identity: identityC, question: "C" });
        }
      },
      onActiveChange: (activeIdentity) => activeChanges.push(activeIdentity),
    });

    controller.start({ identity: identityA, question: "A" });
    controller.start({ identity: identityB, question: "B" });

    expect(deferred.runs.map((run) => run.question)).toEqual(["A", "C"]);
    expect(deferred.runs[0].signal.aborted).toBe(true);
    expect(deferred.runs[1].signal.aborted).toBe(false);
    expect(activeChanges).toEqual([identityA, identityC]);
    controller.dispose();
  });

  it("uses done.message when a run completes without tokens", () => {
    const harness = createHarness();
    const runIdentity = identity("request-no-token");
    harness.controller.start({ identity: runIdentity, question: "No context" });

    harness.runs[0].emit({
      type: "done",
      data: { status: "no_context", message: "No matching context." },
    });

    expect(harness.updates).toEqual([
      {
        target: {
          conversationId: "conversation-request-no-token",
          answerId: "answer-request-no-token",
        },
        update: { kind: "complete", fallback: "No matching context." },
      },
    ]);
    expect(harness.scheduler.scheduledCount).toBe(0);
    expect(harness.activeChanges).toEqual([runIdentity, null]);
  });

  it("stops once, settles before aborting, and ignores the old rejection", async () => {
    const harness = createHarness();
    const runIdentity = identity("request-stop");
    harness.controller.start({ identity: runIdentity, question: "Stop me" });
    harness.runs[0].signal.addEventListener("abort", () => {
      harness.sequence.push("abort");
    });

    harness.controller.stop();
    expect(harness.updates).toEqual([
      {
        target: {
          conversationId: "conversation-request-stop",
          answerId: "answer-request-stop",
        },
        update: { kind: "stop", fallback: "生成已停止。" },
      },
    ]);
    expect(harness.activeChanges).toEqual([runIdentity, null]);
    expect(harness.runs[0].signal.aborted).toBe(true);
    expect(harness.sequence).toEqual([
      "active:request-stop",
      "update:stop",
      "active:null",
      "abort",
    ]);

    harness.controller.stop();
    harness.runs[0].emit({
      type: "error",
      data: { code: "late", message: "late", partial: true, retryable: false },
    });
    harness.runs[0].reject(new DOMException("aborted", "AbortError"));
    await runPromiseHandlers();
    expect(harness.updates).toHaveLength(1);
    expect(harness.activeChanges).toEqual([runIdentity, null]);
  });

  it("settles and aborts A before starting B, isolating all late A activity", async () => {
    const harness = createHarness();
    const identityA = identity("request-a", "answer-a");
    const identityB = identity("request-b", "answer-b");
    harness.controller.start({ identity: identityA, question: "A" });

    harness.controller.start({ identity: identityB, question: "B" });
    expect(harness.runs).toHaveLength(2);
    expect(harness.runs[0].signal.aborted).toBe(true);
    expect(harness.activeChanges).toEqual([identityA, null, identityB]);
    expect(harness.updates).toEqual([
      {
        target: { conversationId: "conversation-request-a", answerId: "answer-a" },
        update: { kind: "stop", fallback: "生成已停止。" },
      },
    ]);

    harness.runs[0].emit({ type: "token", data: { text: "late A" } });
    harness.runs[0].reject(new APIError("late A failure", "late_a"));
    await runPromiseHandlers();
    expect(harness.updates).toHaveLength(1);
    expect(harness.activeChanges).toEqual([identityA, null, identityB]);

    harness.runs[1].emit({ type: "token", data: { text: "B" } });
    harness.runs[1].emit({ type: "done", data: { status: "success" } });
    expect(harness.updates.slice(1)).toEqual([
      {
        target: { conversationId: "conversation-request-b", answerId: "answer-b" },
        update: { kind: "append", text: "B" },
      },
      {
        target: { conversationId: "conversation-request-b", answerId: "answer-b" },
        update: { kind: "complete", fallback: "回答生成完成。" },
      },
    ]);
    expect(harness.activeChanges).toEqual([identityA, null, identityB, null]);
  });

  it("maps an SSE error to one failure terminal", async () => {
    const harness = createHarness();
    const runIdentity = identity("request-sse");
    harness.controller.start({ identity: runIdentity, question: "SSE error" });

    harness.runs[0].emit({
      type: "error",
      data: {
        code: "provider_failed",
        message: "Provider unavailable.",
        partial: false,
        retryable: true,
      },
    });
    harness.runs[0].resolve();
    await runPromiseHandlers();

    expect(harness.updates).toEqual([
      {
        target: {
          conversationId: "conversation-request-sse",
          answerId: "answer-request-sse",
        },
        update: { kind: "fail", message: "Provider unavailable." },
      },
    ]);
    expect(harness.activeChanges).toEqual([runIdentity, null]);
  });

  it.each([
    [new APIError("Backend rejected the request.", "request_failed"), "Backend rejected the request."],
    [new TypeError("fetch failed"), "无法连接问答服务。"],
  ])("maps transport rejection %p to a failure", async (error, expectedMessage) => {
    const harness = createHarness();
    const runIdentity = identity("request-reject");
    harness.controller.start({ identity: runIdentity, question: "Reject" });

    harness.runs[0].reject(error);
    await runPromiseHandlers();

    expect(harness.updates).toEqual([
      {
        target: {
          conversationId: "conversation-request-reject",
          answerId: "answer-request-reject",
        },
        update: { kind: "fail", message: expectedMessage },
      },
    ]);
    expect(harness.activeChanges).toEqual([runIdentity, null]);
  });

  it("treats transport completion without a terminal event as an error", async () => {
    const harness = createHarness();
    const runIdentity = identity("request-eof");
    harness.controller.start({ identity: runIdentity, question: "Unexpected EOF" });

    harness.runs[0].resolve();
    await runPromiseHandlers();

    expect(harness.updates).toEqual([
      {
        target: {
          conversationId: "conversation-request-eof",
          answerId: "answer-request-eof",
        },
        update: { kind: "fail", message: "问答流意外结束，请重试。" },
      },
    ]);
    expect(harness.activeChanges).toEqual([runIdentity, null]);
  });

  it("disposes silently, aborts the run, and permanently rejects callbacks", async () => {
    const harness = createHarness();
    const runIdentity = identity("request-dispose");
    harness.controller.start({ identity: runIdentity, question: "Dispose" });
    harness.runs[0].emit({ type: "token", data: { text: "kept" } });

    harness.controller.dispose();
    expect(harness.runs[0].signal.aborted).toBe(true);
    expect(harness.updates).toEqual([
      {
        target: {
          conversationId: "conversation-request-dispose",
          answerId: "answer-request-dispose",
        },
        update: { kind: "append", text: "kept" },
      },
    ]);
    expect(harness.activeChanges).toEqual([runIdentity]);

    harness.runs[0].emit({ type: "token", data: { text: "discarded" } });
    harness.runs[0].reject(new APIError("discarded", "discarded"));
    await runPromiseHandlers();
    harness.controller.stop();
    harness.controller.start({ identity: identity("request-after-dispose"), question: "No-op" });

    expect(harness.runs).toHaveLength(1);
    expect(harness.updates).toHaveLength(1);
    expect(harness.activeChanges).toEqual([runIdentity]);
  });
});
