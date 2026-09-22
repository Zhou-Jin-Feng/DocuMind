import { Clock3, MessageSquarePlus, Trash2, X } from "lucide-react";
import {
  hasConversationContent,
  type ConversationRecord,
} from "../conversations";

function shortDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export function ConversationHistory({
  conversations,
  activeId,
  onSelect,
  onDelete,
  onClear,
}: {
  conversations: ConversationRecord[];
  activeId: string;
  onSelect: (conversation: ConversationRecord) => void;
  onDelete: (conversationId: string) => void;
  onClear: () => void;
}) {
  const history = conversations
    .filter(hasConversationContent)
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));

  return (
    <section className="conversation-section" aria-labelledby="conversation-history-title">
      <header className="section-heading">
        <div>
          <span id="conversation-history-title">最近对话</span>
          <small>{history.length} 条</small>
        </div>
        <button
          className="icon-button"
          type="button"
          title="清空对话历史"
          aria-label="清空对话历史"
          onClick={onClear}
          disabled={history.length === 0}
        >
          <Trash2 size={15} />
        </button>
      </header>
      <div className="conversation-list">
        {history.map((conversation) => (
          <div
            className={`conversation-item ${conversation.id === activeId ? "active" : ""}`}
            key={conversation.id}
          >
            <button
              className="conversation-select"
              type="button"
              onClick={() => onSelect(conversation)}
              aria-label={`打开对话 ${conversation.title}`}
              aria-current={conversation.id === activeId ? "page" : undefined}
            >
              <MessageSquarePlus size={14} aria-hidden="true" />
              <span>
                <strong title={conversation.title}>{conversation.title}</strong>
                <small>{shortDate(conversation.updatedAt)}</small>
              </span>
            </button>
            <button
              className="conversation-delete"
              type="button"
              title={`删除对话 ${conversation.title}`}
              aria-label={`删除对话 ${conversation.title}`}
              onClick={() => onDelete(conversation.id)}
            >
              <X size={13} />
            </button>
          </div>
        ))}
        {history.length === 0 && (
          <div className="conversation-empty">
            <Clock3 size={16} />
            <span>暂无历史对话</span>
          </div>
        )}
      </div>
    </section>
  );
}
