import { describe, expect, it } from "vitest";
import type { ConversationRecord } from "../../conversations";
import type { ChatMessage, ChatStage, SourceReference } from "../../types";
import {
  conversationReducer,
  type AnswerUpdate,
  type ConversationState,
} from "./conversationState";

function message(
  id: string,
  role: ChatMessage["role"],
  content: string,
  stage: ChatStage = "done",
  sources: SourceReference[] = [],
): ChatMessage {
  return { id, role, content, stage, sources };
}

function conversation(
  id: string,
  messages: ChatMessage[] = [],
  updatedAt = `2026-09-20T00:00:00.000Z`,
): ConversationRecord {
  return {
    id,
    title: messages.find((item) => item.role === "user")?.content || "新对话",
    messages,
    updatedAt,
  };
}

function state(...items: ConversationRecord[]): ConversationState {
  return { activeId: items[0].id, items };
}

describe("conversation reducer", () => {
  it("starts a turn atomically in the explicit conversation", () => {
    const conversationA = conversation("conversation-a", [
      message("question-a", "user", "Existing question"),
    ]);
    const conversationB = conversation("conversation-b");
    const current = state(conversationA, conversationB);

    const next = conversationReducer(current, {
      type: "turn/start",
      conversationId: conversationB.id,
      userId: "question-b",
      answerId: "answer-b",
      question: "  Milvus   如何建立索引？  ",
      at: "2026-09-20T01:00:00.000Z",
    });

    expect(next.activeId).toBe(conversationA.id);
    expect(next.items[0]).toBe(conversationA);
    expect(next.items[1]).not.toBe(conversationB);
    expect(next.items[1]).toMatchObject({
      title: "Milvus 如何建立索引？",
      updatedAt: "2026-09-20T01:00:00.000Z",
    });
    expect(next.items[1].messages).toEqual([
      {
        id: "question-b",
        role: "user",
        content: "  Milvus   如何建立索引？  ",
        stage: "done",
        sources: [],
      },
      {
        id: "answer-b",
        role: "assistant",
        content: "",
        stage: "retrieving",
        sources: [],
      },
    ]);
  });

  it("rejects missing conversations and duplicate message identities by reference", () => {
    const current = state(
      conversation("conversation-a", [
        message("existing", "user", "Existing"),
      ]),
    );

    const missing = conversationReducer(current, {
      type: "turn/start",
      conversationId: "missing",
      userId: "question",
      answerId: "answer",
      question: "Question",
      at: "2026-09-20T01:00:00.000Z",
    });
    const duplicate = conversationReducer(current, {
      type: "turn/start",
      conversationId: "conversation-a",
      userId: "existing",
      answerId: "answer",
      question: "Question",
      at: "2026-09-20T01:00:00.000Z",
    });

    expect(missing).toBe(current);
    expect(duplicate).toBe(current);
  });

  it("updates A by explicit identity after selecting B and preserves non-target references", () => {
    const userA = message("question-a", "user", "Question A");
    const answerA = message("answer-a", "assistant", "partial", "generating");
    const conversationA = conversation("conversation-a", [userA, answerA]);
    const conversationB = conversation("conversation-b", [
      message("question-b", "user", "Question B"),
    ]);
    const current = state(conversationA, conversationB);
    const selected = conversationReducer(current, {
      type: "conversation/select",
      conversationId: conversationB.id,
    });

    const next = conversationReducer(selected, {
      type: "answer/update",
      target: { conversationId: conversationA.id, answerId: answerA.id },
      update: { kind: "append", text: " answer" },
      at: "2026-09-20T01:01:00.000Z",
    });

    expect(next.activeId).toBe(conversationB.id);
    expect(next.items[1]).toBe(conversationB);
    expect(next.items[1].messages).toBe(conversationB.messages);
    expect(next.items[0]).not.toBe(conversationA);
    expect(next.items[0].messages[0]).toBe(userA);
    expect(next.items[0].messages[1]).not.toBe(answerA);
    expect(next.items[0].messages[1].content).toBe("partial answer");
    expect(next.items[0].updatedAt).toBe("2026-09-20T01:01:00.000Z");
  });

  it("returns the same state for a missing answer without touching timestamps", () => {
    const conversationA = conversation("conversation-a", [], "original-a");
    const conversationB = conversation("conversation-b", [], "original-b");
    const current = state(conversationA, conversationB);

    const next = conversationReducer(current, {
      type: "answer/update",
      target: { conversationId: conversationA.id, answerId: "missing" },
      update: { kind: "append", text: "late" },
      at: "new-time",
    });

    expect(next).toBe(current);
    expect(conversationA.updatedAt).toBe("original-a");
    expect(conversationB.updatedAt).toBe("original-b");
  });

  it("ignores late updates after deleting or clearing their answer", () => {
    const answerA = message("answer-a", "assistant", "partial", "generating");
    const conversationA = conversation("conversation-a", [answerA]);
    const conversationB = conversation("conversation-b");
    const current = state(conversationA, conversationB);
    const fallback = conversation("fallback");
    const deleted = conversationReducer(current, {
      type: "conversation/delete",
      conversationId: conversationA.id,
      fallback,
    });
    const afterDelete = conversationReducer(deleted, {
      type: "answer/update",
      target: { conversationId: conversationA.id, answerId: answerA.id },
      update: { kind: "append", text: "late" },
      at: "new-time",
    });

    expect(afterDelete).toBe(deleted);
    expect(deleted.items[0]).toBe(conversationB);

    const cleared = conversationReducer(current, {
      type: "conversation/clear",
      conversationId: conversationA.id,
      at: "clear-time",
    });
    const afterClear = conversationReducer(cleared, {
      type: "answer/update",
      target: { conversationId: conversationA.id, answerId: answerA.id },
      update: { kind: "append", text: "late" },
      at: "new-time",
    });

    expect(afterClear).toBe(cleared);
    expect(cleared.items[1]).toBe(conversationB);
  });

  it("retains the latest answer when deleting an inactive conversation", () => {
    const answerA = message("answer-a", "assistant", "first", "generating");
    const conversationA = conversation("conversation-a", [answerA]);
    const conversationB = conversation("conversation-b", [
      message("question-b", "user", "Question B"),
    ]);
    const appended = conversationReducer(state(conversationA, conversationB), {
      type: "answer/update",
      target: { conversationId: conversationA.id, answerId: answerA.id },
      update: { kind: "append", text: " second" },
      at: "append-time",
    });
    const latestA = appended.items[0];

    const deleted = conversationReducer(appended, {
      type: "conversation/delete",
      conversationId: conversationB.id,
      fallback: conversation("fallback"),
    });

    expect(deleted.activeId).toBe(conversationA.id);
    expect(deleted.items).toEqual([latestA]);
    expect(deleted.items[0]).toBe(latestA);
    expect(deleted.items[0].messages[0].content).toBe("first second");
  });

  it.each(["done", "error"] as const)(
    "treats %s as terminal for every late answer update",
    (terminalStage) => {
      const source: SourceReference = {
        rank: 1,
        source: "guide.txt",
        excerpt: "Guide",
      };
      const answer = message(
        "answer-a",
        "assistant",
        "final",
        terminalStage,
      );
      const current = state(conversation("conversation-a", [answer]));
      const updates: AnswerUpdate[] = [
        { kind: "status", stage: "generating" },
        { kind: "sources", items: [source] },
        { kind: "append", text: "late" },
        { kind: "complete", fallback: "late" },
        { kind: "fail", message: "late" },
        { kind: "stop", fallback: "late" },
      ];

      for (const update of updates) {
        expect(
          conversationReducer(current, {
            type: "answer/update",
            target: {
              conversationId: "conversation-a",
              answerId: answer.id,
            },
            update,
            at: "new-time",
          }),
        ).toBe(current);
      }
    },
  );

  it("returns the same state for empty appends and unchanged status/source references", () => {
    const sources: SourceReference[] = [];
    const answer = message(
      "answer-a",
      "assistant",
      "partial",
      "generating",
      sources,
    );
    const current = state(conversation("conversation-a", [answer]));
    const target = { conversationId: "conversation-a", answerId: answer.id };

    expect(
      conversationReducer(current, {
        type: "answer/update",
        target,
        update: { kind: "append", text: "" },
        at: "new-time",
      }),
    ).toBe(current);
    expect(
      conversationReducer(current, {
        type: "answer/update",
        target,
        update: { kind: "status", stage: "generating" },
        at: "new-time",
      }),
    ).toBe(current);
    expect(
      conversationReducer(current, {
        type: "answer/update",
        target,
        update: { kind: "sources", items: sources },
        at: "new-time",
      }),
    ).toBe(current);
  });

  it("preserves partial text and applies complete, stop, and failure terminal semantics", () => {
    const target = { conversationId: "conversation-a", answerId: "answer-a" };
    const initial = state(
      conversation("conversation-a", [
        message("answer-a", "assistant", "partial", "generating"),
      ]),
    );

    const completed = conversationReducer(initial, {
      type: "answer/update",
      target,
      update: { kind: "complete", fallback: "fallback" },
      at: "complete-time",
    });
    expect(completed.items[0].messages[0]).toMatchObject({
      content: "partial",
      stage: "done",
    });

    const stopped = conversationReducer(
      state(
        conversation("conversation-a", [
          message("answer-a", "assistant", "", "retrieving"),
        ]),
      ),
      {
        type: "answer/update",
        target,
        update: { kind: "stop" },
        at: "stop-time",
      },
    );
    expect(stopped.items[0].messages[0]).toMatchObject({
      content: "生成已停止。",
      stage: "done",
    });

    const failed = conversationReducer(initial, {
      type: "answer/update",
      target,
      update: { kind: "fail", message: "网络错误" },
      at: "fail-time",
    });
    expect(failed.items[0].messages[0]).toMatchObject({
      content: "partial\n\n> 网络错误",
      stage: "error",
    });
  });

  it("uses complete fallback only when no answer text was received", () => {
    const current = state(
      conversation("conversation-a", [
        message("answer-a", "assistant", "", "generating"),
      ]),
    );
    const next = conversationReducer(current, {
      type: "answer/update",
      target: { conversationId: "conversation-a", answerId: "answer-a" },
      update: { kind: "complete", fallback: "No context." },
      at: "complete-time",
    });

    expect(next.items[0].messages[0]).toMatchObject({
      content: "No context.",
      stage: "done",
    });
  });

  it("maintains a valid active conversation across new, select, delete, clear, and clear-all", () => {
    const history = conversation("history", [
      message("history-question", "user", "History"),
    ]);
    const empty = conversation("empty");
    const current = state(empty, history);
    const replacement = conversation("replacement");

    const afterNew = conversationReducer(current, {
      type: "conversation/new",
      conversation: replacement,
    });
    expect(afterNew.activeId).toBe(replacement.id);
    expect(afterNew.items).toEqual([replacement, history]);

    const afterSelect = conversationReducer(afterNew, {
      type: "conversation/select",
      conversationId: history.id,
    });
    expect(afterSelect.activeId).toBe(history.id);
    expect(afterSelect.items).toBe(afterNew.items);

    const afterClear = conversationReducer(afterSelect, {
      type: "conversation/clear",
      conversationId: history.id,
      at: "clear-time",
    });
    expect(afterClear.items[1]).toMatchObject({
      id: history.id,
      title: "新对话",
      messages: [],
      updatedAt: "clear-time",
    });

    const afterDelete = conversationReducer(afterClear, {
      type: "conversation/delete",
      conversationId: history.id,
      fallback: conversation("unused"),
    });
    expect(afterDelete.activeId).toBe(replacement.id);
    expect(afterDelete.items).toEqual([replacement]);

    const fallback = conversation("fallback");
    const afterClearAll = conversationReducer(afterDelete, {
      type: "conversation/clear-all",
      fallback,
    });
    expect(afterClearAll).toEqual({ activeId: fallback.id, items: [fallback] });
  });

  it("keeps state by reference for unknown conversation commands and duplicate new IDs", () => {
    const current = state(conversation("conversation-a"));

    expect(
      conversationReducer(current, {
        type: "conversation/select",
        conversationId: "missing",
      }),
    ).toBe(current);
    expect(
      conversationReducer(current, {
        type: "conversation/delete",
        conversationId: "missing",
        fallback: conversation("fallback"),
      }),
    ).toBe(current);
    expect(
      conversationReducer(current, {
        type: "conversation/new",
        conversation: conversation("conversation-a"),
      }),
    ).toBe(current);
  });
});
