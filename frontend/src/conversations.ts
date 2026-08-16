import type { ChatMessage } from "./types";

export const CONVERSATION_STORAGE_KEY = "rag-workbench-conversations-v1";
export const MAX_SAVED_CONVERSATIONS = 12;
const MAX_SAVED_MESSAGES = 60;

export interface ConversationRecord {
  id: string;
  title: string;
  messages: ChatMessage[];
  updatedAt: string;
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") return false;
  const message = value as Partial<ChatMessage>;
  return (
    typeof message.id === "string" &&
    (message.role === "user" || message.role === "assistant") &&
    typeof message.content === "string" &&
    typeof message.stage === "string" &&
    Array.isArray(message.sources)
  );
}

function isConversation(value: unknown): value is ConversationRecord {
  if (!value || typeof value !== "object") return false;
  const conversation = value as Partial<ConversationRecord>;
  return (
    typeof conversation.id === "string" &&
    typeof conversation.title === "string" &&
    typeof conversation.updatedAt === "string" &&
    Array.isArray(conversation.messages) &&
    conversation.messages.every(isChatMessage)
  );
}

export function createConversation(): ConversationRecord {
  return {
    id: crypto.randomUUID(),
    title: "新对话",
    messages: [],
    updatedAt: new Date().toISOString(),
  };
}

export function hasConversationContent(conversation: ConversationRecord): boolean {
  return conversation.messages.some((message) => message.role === "user");
}

export function titleFromMessages(messages: ChatMessage[]): string {
  const firstQuestion = messages
    .find((message) => message.role === "user")
    ?.content.trim()
    .replace(/\s+/g, " ");
  if (!firstQuestion) return "新对话";
  return firstQuestion.length > 24
    ? `${firstQuestion.slice(0, 24)}...`
    : firstQuestion;
}

export function loadConversations(storage: Pick<Storage, "getItem">): ConversationRecord[] {
  try {
    const raw = storage.getItem(CONVERSATION_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(isConversation)
      .filter(hasConversationContent)
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
      .slice(0, MAX_SAVED_CONVERSATIONS);
  } catch {
    return [];
  }
}

export function saveConversations(
  storage: Pick<Storage, "setItem">,
  conversations: ConversationRecord[],
): void {
  const records = conversations
    .filter(hasConversationContent)
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
    .slice(0, MAX_SAVED_CONVERSATIONS)
    .map((conversation) => ({
      ...conversation,
      messages: conversation.messages.slice(-MAX_SAVED_MESSAGES),
    }));
  try {
    storage.setItem(CONVERSATION_STORAGE_KEY, JSON.stringify(records));
  } catch {
    // Storage can be unavailable or full; the active in-memory conversation still works.
  }
}
