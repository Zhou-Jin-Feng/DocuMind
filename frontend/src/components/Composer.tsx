import type {
  FormEventHandler,
  KeyboardEventHandler,
  RefObject,
} from "react";
import { Send, Square } from "lucide-react";

export function Composer({
  question,
  serviceReady,
  streaming,
  collectionName,
  textareaRef,
  onQuestionChange,
  onKeyDown,
  onSubmit,
  onStop,
}: {
  question: string;
  serviceReady: boolean;
  streaming: boolean;
  collectionName: string;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  onQuestionChange: (value: string) => void;
  onKeyDown: KeyboardEventHandler<HTMLTextAreaElement>;
  onSubmit: FormEventHandler<HTMLFormElement>;
  onStop: () => void;
}) {
  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        ref={textareaRef}
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="向知识库提问"
        rows={2}
        maxLength={4000}
        disabled={!serviceReady}
      />
      {streaming ? (
        <button
          className="send-button stop-button"
          type="button"
          onClick={onStop}
          title="停止生成"
        >
          <Square size={16} fill="currentColor" />
          停止
        </button>
      ) : (
        <button
          className="send-button"
          type="submit"
          disabled={!question.trim() || !serviceReady}
        >
          <Send size={17} />
          发送
        </button>
      )}
      <div className="composer-meta">
        <span>{collectionName}</span>
        <span>{question.length}/4000</span>
      </div>
    </form>
  );
}
