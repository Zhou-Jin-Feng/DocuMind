import {
  memo,
  useEffect,
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type AnchorHTMLAttributes,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { ArrowDown, Bot, LoaderCircle } from "lucide-react";
import { recordFe01MessageRender } from "../fe01Metrics";
import type { ChatMessage } from "../types";
import { createCitationRemarkPlugin, HIGHLIGHT_OPTIONS } from "../features/chat/markdown";

const FE01_PROFILE_ENABLED = import.meta.env.VITE_FE01_PROFILE === "1";
const MARKDOWN_REMARK_PLUGINS = [remarkGfm];
const REHYPE_HIGHLIGHT_TRANSFORM = rehypeHighlight(HIGHLIGHT_OPTIONS);
const REHYPE_HIGHLIGHT_PLUGIN = () => REHYPE_HIGHLIGHT_TRANSFORM;
const FOLLOW_BOTTOM_THRESHOLD_PX = 64;

export const MessageItem = memo(function MessageItem({
  message,
  onOpenSources,
}: {
  message: ChatMessage;
  onOpenSources: (answerId: string, sourceRank?: number) => void;
}) {
  if (FE01_PROFILE_ENABLED) recordFe01MessageRender(message);
  const citationPlugin = useMemo(() => createCitationRemarkPlugin(message.sources), [message.sources]);
  const validCitationRanks = useMemo(() => new Set(message.sources.map((source) => source.rank)), [message.sources]);
  const handleCitation = useCallback(
    (rank: number) => onOpenSources(message.id, rank),
    [message.id, onOpenSources],
  );
 const markdownComponents = useMemo(
    () => ({
      a: ({ href, children, node: markdownNode, ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { node?: { properties?: Record<string, unknown> } }) => {
        const properties = markdownNode?.properties ?? {};
        const marked = properties["data-documind-citation"] === "true";
        const rawRank = properties["data-documind-citation-rank"];
        const rank = typeof rawRank === "string" ? Number(rawRank) : NaN;
        const valid = marked && /^[1-9]\d*$/.test(String(rawRank)) && Number.isSafeInteger(rank) && validCitationRanks.has(rank);
        if (!valid) return <a href={href} {...props}>{children}</a>;
        return (
          <button
            type="button"
            className="citation-chip"
            aria-label={"查看引用文档" + rank}
            onClick={() => handleCitation(rank)}
          >
            {children}
          </button>
        );
      },
    }),
    [handleCitation, validCitationRanks],
  );
  const stableStage = message.stage === "done" || message.stage === "error";
  const [highlightReady, setHighlightReady] = useState(stableStage);
  useEffect(() => {
    if (!stableStage) {
      setHighlightReady(false);
      return;
    }
    if (highlightReady) return;
    const frame = window.requestAnimationFrame(() => setHighlightReady(true));
    return () => window.cancelAnimationFrame(frame);
  }, [highlightReady, stableStage]);
  const rehypePlugins = highlightReady
    ? [REHYPE_HIGHLIGHT_PLUGIN]
    : [];

  return (
    <article className={`message message-${message.role}`}>
      {message.role === "assistant" && (
        <div className="assistant-avatar" aria-hidden="true">
          <Bot size={17} />
        </div>
      )}
      <div className={`message-body ${message.stage === "error" ? "message-error" : ""}`}>
        {message.role === "assistant" && message.stage !== "done" && !message.content && (
          <div className="message-progress">
            <LoaderCircle className="spin" size={16} />
            {message.stage === "retrieving" ? "正在检索知识库" : "正在生成回答"}
          </div>
        )}
        {message.content && (
          <ReactMarkdown
           remarkPlugins={[MARKDOWN_REMARK_PLUGINS[0], citationPlugin]}
            rehypePlugins={rehypePlugins}
            components={markdownComponents}
          >
            {message.content}
          </ReactMarkdown>
        )}
        {message.role === "assistant" && message.sources.length > 0 && (
          <button
            type="button"
            className="citation-link"
            onClick={() => onOpenSources(message.id)}
          >
            {message.sources.length} 条引用来源
          </button>
        )}
      </div>
    </article>
  );
});

export function MessageList({
  messages,
  documentCount,
  conversationId,
  onOpenSources,
  onPromptSelect,
}: {
  messages: ChatMessage[];
  documentCount: number;
  conversationId: string;
  onOpenSources: (answerId: string, sourceRank?: number) => void;
  onPromptSelect: (prompt: string) => void;
}) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const followingRef = useRef(true);
  const programmaticScrollRef = useRef(false);
  const showBackToLatestRef = useRef(false);
  const previousConversationIdRef = useRef<string | null>(null);
  const previousTailIdRef = useRef<string | null>(null);
  const [showBackToLatest, setShowBackToLatest] = useState(false);
  const tailId = messages.at(-1)?.id ?? null;

  function updateBackToLatestVisibility(visible: boolean): void {
    if (showBackToLatestRef.current === visible) return;
    showBackToLatestRef.current = visible;
    setShowBackToLatest(visible);
  }

  useLayoutEffect(() => {
    const contextChanged =
      previousConversationIdRef.current !== conversationId ||
      previousTailIdRef.current !== tailId;
    previousConversationIdRef.current = conversationId;
    previousTailIdRef.current = tailId;

    if (contextChanged) {
      followingRef.current = true;
      programmaticScrollRef.current = false;
      updateBackToLatestVisibility(false);
    }

    const list = listRef.current;
    if (list && followingRef.current) {
      list.scrollTop = list.scrollHeight;
    }
  }, [conversationId, messages, tailId]);

  function markUserScrollIntent(): void {
    programmaticScrollRef.current = false;
  }

  function handleScroll(): void {
    const list = listRef.current;
    if (!list) return;
    const nearBottom =
      list.scrollHeight - list.clientHeight - list.scrollTop <=
      FOLLOW_BOTTOM_THRESHOLD_PX;

    if (programmaticScrollRef.current) {
      followingRef.current = true;
      updateBackToLatestVisibility(false);
      if (nearBottom) programmaticScrollRef.current = false;
      return;
    }

    followingRef.current = nearBottom;
    updateBackToLatestVisibility(!nearBottom);
  }

  function returnToLatest(): void {
    const list = listRef.current;
    if (!list) return;
    followingRef.current = true;
    programmaticScrollRef.current = true;
    list.focus({ preventScroll: true });
    updateBackToLatestVisibility(false);
    list.scrollTo({
      top: list.scrollHeight,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }

  return (
    <div className="message-list-shell">
      <div
        ref={listRef}
        className="message-list"
        aria-label="对话消息"
        tabIndex={0}
        onScroll={handleScroll}
        onWheel={markUserScrollIntent}
        onTouchStart={markUserScrollIntent}
        onPointerDown={markUserScrollIntent}
        onKeyDown={markUserScrollIntent}
      >
        {messages.length === 0 && (
          <div className="chat-empty">
            <div aria-hidden="true">
              <Bot size={22} />
            </div>
            <strong>暂无对话</strong>
            <span>
              {documentCount > 0 ? `知识库中有 ${documentCount} 个文档` : "知识库暂无文档"}
            </span>
            {documentCount > 0 && (
              <div className="chat-empty-actions" aria-label="建议问题">
                {["这份知识库主要讲什么？", "总结文档中的关键结论", "有哪些重要术语？"].map(
                  (prompt) => (
                    <button key={prompt} type="button" onClick={() => onPromptSelect(prompt)}>
                      {prompt}
                    </button>
                  ),
                )}
              </div>
            )}
          </div>
        )}
        {messages.map((message) => (
          <MessageItem key={message.id} message={message} onOpenSources={onOpenSources} />
        ))}
      </div>
      {showBackToLatest && (
        <button
          type="button"
          className="back-to-latest"
          onClick={returnToLatest}
        >
          <ArrowDown size={15} />
          回到最新
        </button>
      )}
    </div>
  );
}
