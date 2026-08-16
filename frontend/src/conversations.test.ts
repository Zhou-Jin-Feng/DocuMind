import { describe, expect, it } from "vitest";
import {
  CONVERSATION_STORAGE_KEY,
  hasConversationContent,
  loadConversations,
  saveConversations,
  titleFromMessages,
  type ConversationRecord,
} from "./conversations";
import type { ChatMessage } from "./types";

function message(role: ChatMessage["role"], content: string): ChatMessage {
  return {
    id: `${role}-${content}`,
    role,
    content,
    stage: "done",
    sources: [],
  };
}

describe("conversation history", () => {
  it("uses the first question as a compact title", () => {
    expect(titleFromMessages([message("assistant", "回答")])).toBe("新对话");
    expect(titleFromMessages([message("user", "  Milvus   如何建立索引？  ")])).toBe(
      "Milvus 如何建立索引？",
    );
    expect(titleFromMessages([message("user", "1234567890123456789012345")])).toBe(
      "123456789012345678901234...",
    );
  });

  it("persists only conversations that contain a question", () => {
    const stored = new Map<string, string>();
    const storage = {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => stored.set(key, value),
    };
    const conversations: ConversationRecord[] = [
      {
        id: "empty",
        title: "新对话",
        messages: [],
        updatedAt: "2026-08-16T08:00:00.000Z",
      },
      {
        id: "saved",
        title: "什么是 RAG？",
        messages: [message("user", "什么是 RAG？")],
        updatedAt: "2026-08-16T08:01:00.000Z",
      },
    ];

    saveConversations(storage, conversations);

    expect(stored.has(CONVERSATION_STORAGE_KEY)).toBe(true);
    expect(loadConversations(storage)).toHaveLength(1);
    expect(loadConversations(storage)[0].id).toBe("saved");
    expect(hasConversationContent(conversations[0])).toBe(false);
  });

  it("ignores malformed storage values", () => {
    expect(loadConversations({ getItem: () => "not-json" })).toEqual([]);
    expect(loadConversations({ getItem: () => JSON.stringify([{ id: 1 }]) })).toEqual([]);
  });
});
