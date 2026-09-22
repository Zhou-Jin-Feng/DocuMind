import {
  hasConversationContent,
  titleFromMessages,
  type ConversationRecord,
} from "../../conversations";
import type { ChatMessage, SourceReference } from "../../types";

const COMPLETE_FALLBACK = "回答生成完成。";
const STOP_FALLBACK = "生成已停止。";

export interface ConversationState {
  activeId: string;
  items: ConversationRecord[];
}

export interface AnswerTarget {
  conversationId: string;
  answerId: string;
}

export type AnswerUpdate =
  | { kind: "status"; stage: "retrieving" | "generating" }
  | { kind: "sources"; items: SourceReference[] }
  | { kind: "append"; text: string }
  | { kind: "complete"; fallback?: string }
  | { kind: "fail"; message: string }
  | { kind: "stop"; fallback?: string };

export type ConversationCommand =
  | { type: "conversation/new"; conversation: ConversationRecord }
  | { type: "conversation/select"; conversationId: string }
  | {
      type: "conversation/delete";
      conversationId: string;
      fallback: ConversationRecord;
    }
  | { type: "conversation/clear"; conversationId: string; at: string }
  | { type: "conversation/clear-all"; fallback: ConversationRecord }
  | {
      type: "turn/start";
      conversationId: string;
      userId: string;
      answerId: string;
      question: string;
      at: string;
    }
  | {
      type: "answer/update";
      target: AnswerTarget;
      update: AnswerUpdate;
      at: string;
    };

function hasMessageId(state: ConversationState, messageId: string): boolean {
  return state.items.some((conversation) =>
    conversation.messages.some((message) => message.id === messageId),
  );
}

function replaceConversation(
  state: ConversationState,
  conversationIndex: number,
  conversation: ConversationRecord,
): ConversationState {
  const items = [...state.items];
  items[conversationIndex] = conversation;
  return { ...state, items };
}

function startTurn(
  state: ConversationState,
  command: Extract<ConversationCommand, { type: "turn/start" }>,
): ConversationState {
  const conversationIndex = state.items.findIndex(
    (conversation) => conversation.id === command.conversationId,
  );
  if (
    conversationIndex < 0 ||
    command.userId === command.answerId ||
    hasMessageId(state, command.userId) ||
    hasMessageId(state, command.answerId)
  ) {
    return state;
  }

  const conversation = state.items[conversationIndex];
  const userMessage: ChatMessage = {
    id: command.userId,
    role: "user",
    content: command.question,
    stage: "done",
    sources: [],
  };
  const answerMessage: ChatMessage = {
    id: command.answerId,
    role: "assistant",
    content: "",
    stage: "retrieving",
    sources: [],
  };
  const messages = [...conversation.messages, userMessage, answerMessage];

  return replaceConversation(state, conversationIndex, {
    ...conversation,
    messages,
    title: titleFromMessages(messages),
    updatedAt: command.at,
  });
}

function updateAnswer(
  state: ConversationState,
  command: Extract<ConversationCommand, { type: "answer/update" }>,
): ConversationState {
  const conversationIndex = state.items.findIndex(
    (conversation) => conversation.id === command.target.conversationId,
  );
  if (conversationIndex < 0) return state;

  const conversation = state.items[conversationIndex];
  const messageIndex = conversation.messages.findIndex(
    (message) =>
      message.id === command.target.answerId && message.role === "assistant",
  );
  if (messageIndex < 0) return state;

  const message = conversation.messages[messageIndex];
  if (message.stage === "done" || message.stage === "error") return state;

  let nextMessage: ChatMessage;
  switch (command.update.kind) {
    case "status":
      if (message.stage === command.update.stage) return state;
      nextMessage = { ...message, stage: command.update.stage };
      break;
    case "sources":
      if (message.sources === command.update.items) return state;
      nextMessage = { ...message, sources: command.update.items };
      break;
    case "append":
      if (!command.update.text) return state;
      nextMessage = {
        ...message,
        content: message.content + command.update.text,
        stage: "generating",
      };
      break;
    case "complete":
      nextMessage = {
        ...message,
        content: message.content || command.update.fallback || COMPLETE_FALLBACK,
        stage: "done",
      };
      break;
    case "fail":
      nextMessage = {
        ...message,
        content: message.content
          ? `${message.content}\n\n> ${command.update.message}`
          : command.update.message,
        stage: "error",
      };
      break;
    case "stop":
      nextMessage = {
        ...message,
        content: message.content || command.update.fallback || STOP_FALLBACK,
        stage: "done",
      };
      break;
  }

  const messages = [...conversation.messages];
  messages[messageIndex] = nextMessage;
  return replaceConversation(state, conversationIndex, {
    ...conversation,
    messages,
    updatedAt: command.at,
  });
}

export function conversationReducer(
  state: ConversationState,
  command: ConversationCommand,
): ConversationState {
  switch (command.type) {
    case "conversation/new": {
      if (state.items.some((item) => item.id === command.conversation.id)) {
        return state;
      }

      const activeIndex = state.items.findIndex((item) => item.id === state.activeId);
      if (
        activeIndex >= 0 &&
        !hasConversationContent(state.items[activeIndex])
      ) {
        const items = [...state.items];
        items[activeIndex] = command.conversation;
        return { activeId: command.conversation.id, items };
      }

      return {
        activeId: command.conversation.id,
        items: [command.conversation, ...state.items],
      };
    }
    case "conversation/select":
      if (
        command.conversationId === state.activeId ||
        !state.items.some((item) => item.id === command.conversationId)
      ) {
        return state;
      }
      return { ...state, activeId: command.conversationId };
    case "conversation/delete": {
      const conversationIndex = state.items.findIndex(
        (item) => item.id === command.conversationId,
      );
      if (conversationIndex < 0) return state;

      const items = state.items.filter((_, index) => index !== conversationIndex);
      if (items.length === 0) {
        return { activeId: command.fallback.id, items: [command.fallback] };
      }
      return {
        activeId:
          state.activeId === command.conversationId
            ? items[0].id
            : state.activeId,
        items,
      };
    }
    case "conversation/clear": {
      const conversationIndex = state.items.findIndex(
        (item) => item.id === command.conversationId,
      );
      if (conversationIndex < 0) return state;

      return replaceConversation(state, conversationIndex, {
        ...state.items[conversationIndex],
        title: "新对话",
        messages: [],
        updatedAt: command.at,
      });
    }
    case "conversation/clear-all":
      return { activeId: command.fallback.id, items: [command.fallback] };
    case "turn/start":
      return startTurn(state, command);
    case "answer/update":
      return updateAnswer(state, command);
  }
}
