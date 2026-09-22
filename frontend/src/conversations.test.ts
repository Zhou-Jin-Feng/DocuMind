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

  it("loads conversations written by the 3.0.0 storage format", () => {
    const legacyConversation: ConversationRecord = {
      id: "conversation-3-0-0",
      title: "旧版本对话",
      updatedAt: "2026-08-16T08:01:00.000Z",
      messages: [
        message("user", "旧版本问题"),
        {
          id: "assistant-3-0-0",
          role: "assistant",
          content: "旧版本部分回答",
          stage: "generating",
          sources: [
            {
              rank: 1,
              source: "legacy.txt",
              page_number: 2,
              excerpt: "3.0.0 保存的引用片段",
              distance: 0.125,
              chunk_id: "legacy-chunk",
            },
          ],
        },
      ],
    };
    const storage = {
      getItem: (key: string) =>
        key === CONVERSATION_STORAGE_KEY
          ? JSON.stringify([legacyConversation])
          : null,
    };

    expect(loadConversations(storage)).toEqual([legacyConversation]);
  });

  it("keeps the existing storage key and 12 conversation / 60 message limits", () => {
    const stored = new Map<string, string>();
    const storage = {
      getItem: (key: string) => stored.get(key) ?? null,
      setItem: (key: string, value: string) => stored.set(key, value),
    };
    const conversations = Array.from({ length: 13 }, (_, conversationIndex) => ({
      id: `conversation-${conversationIndex}`,
      title: `Conversation ${conversationIndex}`,
      messages: Array.from({ length: 61 }, (_, messageIndex) =>
        message("user", `${conversationIndex}-${messageIndex}`),
      ),
      updatedAt: new Date(
        Date.UTC(2026, 0, 1, 0, 0, conversationIndex),
      ).toISOString(),
    }));

    saveConversations(storage, conversations);

    expect([...stored.keys()]).toEqual([CONVERSATION_STORAGE_KEY]);
    const persisted = JSON.parse(
      stored.get(CONVERSATION_STORAGE_KEY) as string,
    ) as ConversationRecord[];
    expect(persisted).toHaveLength(12);
    expect(persisted[0].id).toBe("conversation-12");
    expect(persisted.every((item) => item.messages.length === 60)).toBe(true);
    expect(persisted[0].messages[0].content).toBe("12-1");
    expect(loadConversations(storage)).toEqual(persisted);
  });

  it("ignores malformed storage values", () => {
    expect(loadConversations({ getItem: () => "not-json" })).toEqual([]);
    expect(loadConversations({ getItem: () => JSON.stringify([{ id: 1 }]) })).toEqual([]);
  });
});
