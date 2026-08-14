import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  Check,
  CircleAlert,
  Database,
  FileText,
  LibraryBig,
  LoaderCircle,
  MessageSquarePlus,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Send,
  Server,
  Square,
  Upload,
  X,
} from "lucide-react";
import {
  APIError,
  getDocuments,
  getPublicConfig,
  getReadiness,
  streamChat,
  uploadDocument,
} from "./api";
import type {
  ChatEvent,
  ChatMessage,
  DocumentRecord,
  SourceReference,
} from "./types";

const INITIAL_ASSISTANT_MESSAGE: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content: "RAG 工作台已启动。",
  stage: "done",
  sources: [],
};

const QUERY_RETRY_COUNT = 2;
const QUERY_REFRESH_INTERVAL = 30_000;

function formatBytes(value?: number | null): string {
  if (!value) return "--";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

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

function updateMessage(
  messages: ChatMessage[],
  id: string,
  update: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return messages.map((message) => (message.id === id ? update(message) : message));
}

function statusLabel(status: string): string {
  if (status === "active") return "已索引";
  if (status === "indexing") return "处理中";
  if (status === "failed") return "失败";
  return status;
}

function DocumentItem({ document }: { document: DocumentRecord }) {
  return (
    <article className="document-item">
      <div className="document-icon" aria-hidden="true">
        <FileText size={17} />
      </div>
      <div className="document-copy">
        <strong title={document.display_name}>{document.display_name}</strong>
        <span>
          {document.chunk_count} chunks · {formatBytes(document.file_size_bytes)} · {shortDate(document.updated_at)}
        </span>
      </div>
      <span className={`document-status status-${document.status}`}>
        {statusLabel(document.status)}
      </span>
    </article>
  );
}

function SourceItem({ source }: { source: SourceReference }) {
  const metrics = [
    source.distance != null ? `L2 ${source.distance.toFixed(4)}` : null,
    source.rerank_score != null ? `Rerank ${source.rerank_score.toFixed(4)}` : null,
    source.fusion_score != null ? `RRF ${source.fusion_score.toFixed(5)}` : null,
  ].filter(Boolean);
  return (
    <article className="source-item">
      <header>
        <span className="source-rank">{source.rank}</span>
        <div>
          <strong>{source.source}</strong>
          <span>{source.page_number ? `第 ${source.page_number} 页` : "文档片段"}</span>
        </div>
      </header>
      <p>{source.excerpt}</p>
      {metrics.length > 0 && <footer>{metrics.join(" · ")}</footer>}
    </article>
  );
}

function App() {
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([
    INITIAL_ASSISTANT_MESSAGE,
  ]);
  const [question, setQuestion] = useState("");
  const [activeAnswerId, setActiveAnswerId] = useState<string | null>(null);
  const [selectedSources, setSelectedSources] = useState<SourceReference[]>([]);
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const streamController = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const chatEnd = useRef<HTMLDivElement | null>(null);

  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: getReadiness,
    retry: QUERY_RETRY_COUNT,
    refetchInterval: QUERY_REFRESH_INTERVAL,
  });
  const config = useQuery({
    queryKey: ["public-config"],
    queryFn: getPublicConfig,
    retry: QUERY_RETRY_COUNT,
    refetchInterval: QUERY_REFRESH_INTERVAL,
  });
  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: getDocuments,
    retry: QUERY_RETRY_COUNT,
    refetchInterval: QUERY_REFRESH_INTERVAL,
  });
  const upload = useMutation({
    mutationFn: uploadDocument,
    onSuccess: (result) => {
      setUploadNotice(
        result.status === "noop"
          ? "文档已存在，索引保持不变。"
          : `索引完成，共生成 ${result.chunk_count} 个 chunks。`,
      );
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (error) => {
      setUploadNotice(error instanceof Error ? error.message : "文档上传失败。")
    },
  });

  const isStreaming = activeAnswerId !== null;
  const activeComponents = readiness.data?.components;
  const serviceReady = readiness.data?.ready === true;
  const currentSourceCount = selectedSources.length;
  const documentsTotal = documents.data?.total ?? 0;

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    return () => streamController.current?.abort();
  }, []);

  const providerLabel = useMemo(() => {
    if (config.isError) return "配置不可用";
    if (!config.data) return "配置加载中";
    return `${config.data.embedding_provider} · ${config.data.llm_provider}`;
  }, [config.data, config.isError]);

  function applyChatEvent(answerId: string, event: ChatEvent) {
    if (event.type === "sources") {
      setSelectedSources(event.data.items);
      setMessages((current) =>
        updateMessage(current, answerId, (message) => ({
          ...message,
          sources: event.data.items,
        })),
      );
      return;
    }
    if (event.type === "status") {
      setMessages((current) =>
        updateMessage(current, answerId, (message) => ({
          ...message,
          stage: event.data.stage,
        })),
      );
      return;
    }
    if (event.type === "token") {
      setMessages((current) =>
        updateMessage(current, answerId, (message) => ({
          ...message,
          content: message.content + event.data.text,
          stage: "generating",
        })),
      );
      return;
    }
    if (event.type === "done") {
      setMessages((current) =>
        updateMessage(current, answerId, (message) => ({
          ...message,
          content: message.content || event.data.message || "回答生成完成。",
          stage: "done",
        })),
      );
      return;
    }
    setMessages((current) =>
      updateMessage(current, answerId, (message) => ({
        ...message,
        content: message.content
          ? `${message.content}\n\n> ${event.data.message}`
          : event.data.message,
        stage: "error",
      })),
    );
  }

  async function submitQuestion(event?: FormEvent) {
    event?.preventDefault();
    const normalized = question.trim();
    if (!normalized || isStreaming) return;

    const userId = crypto.randomUUID();
    const answerId = crypto.randomUUID();
    const controller = new AbortController();
    streamController.current = controller;
    setQuestion("");
    setSelectedSources([]);
    setActiveAnswerId(answerId);
    setMessages((current) => [
      ...current,
      { id: userId, role: "user", content: normalized, stage: "done", sources: [] },
      { id: answerId, role: "assistant", content: "", stage: "retrieving", sources: [] },
    ]);

    try {
      await streamChat(
        normalized,
        { onEvent: (chatEvent) => applyChatEvent(answerId, chatEvent) },
        controller.signal,
      );
    } catch (error) {
      if (controller.signal.aborted) {
        setMessages((current) =>
          updateMessage(current, answerId, (message) => ({
            ...message,
            content: message.content || "生成已停止。",
            stage: "done",
          })),
        );
      } else {
        const message =
          error instanceof APIError ? error.message : "无法连接问答服务。";
        setMessages((current) =>
          updateMessage(current, answerId, (item) => ({
            ...item,
            content: item.content ? `${item.content}\n\n> ${message}` : message,
            stage: "error",
          })),
        );
      }
    } finally {
      setActiveAnswerId(null);
      streamController.current = null;
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitQuestion();
    }
  }

  function stopStream() {
    streamController.current?.abort();
  }

  function resetConversation() {
    streamController.current?.abort();
    setActiveAnswerId(null);
    setMessages([INITIAL_ASSISTANT_MESSAGE]);
    setSelectedSources([]);
    setQuestion("");
  }

  function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadNotice(null);
    upload.mutate(file);
    event.target.value = "";
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <LibraryBig size={21} />
          </div>
          <div>
            <strong>RAG Workbench</strong>
            <span>Knowledge operations</span>
          </div>
        </div>

        <button className="new-chat-button" type="button" onClick={resetConversation}>
          <MessageSquarePlus size={17} />
          新建对话
        </button>

        <section className="sidebar-section">
          <header className="section-heading">
            <div>
              <span>知识库</span>
              <small>{documentsTotal} 个文档</small>
            </div>
            <button
              className="icon-button"
              type="button"
              title="刷新文档列表"
              aria-label="刷新文档列表"
              onClick={() => void documents.refetch()}
              disabled={documents.isFetching}
            >
              <RefreshCw size={16} className={documents.isFetching ? "spin" : ""} />
            </button>
          </header>

          <input
            ref={fileInput}
            className="visually-hidden"
            type="file"
            accept={config.data?.allowed_extensions.join(",") || ".pdf,.docx,.txt"}
            onChange={handleFileSelected}
          />
          <button
            className="upload-button"
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={upload.isPending || !serviceReady}
          >
            {upload.isPending ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}
            {upload.isPending ? "正在建立索引" : "上传文档"}
          </button>
          {uploadNotice && (
            <div className={`upload-notice ${upload.isError ? "notice-error" : ""}`}>
              {upload.isError ? <CircleAlert size={15} /> : <Check size={15} />}
              <span>{uploadNotice}</span>
              <button
                className="notice-close"
                type="button"
                title="关闭提示"
                aria-label="关闭提示"
                onClick={() => setUploadNotice(null)}
              >
                <X size={14} />
              </button>
            </div>
          )}

          <div className="document-list">
            {documents.isLoading && (
              <div className="list-placeholder"><LoaderCircle className="spin" size={18} />加载文档</div>
            )}
            {documents.isError && (
              <div className="list-placeholder error-text"><CircleAlert size={18} />文档服务不可用</div>
            )}
            {documents.data?.items.map((document) => (
              <DocumentItem key={document.document_key} document={document} />
            ))}
            {documents.data?.total === 0 && (
              <div className="empty-documents">
                <Database size={22} />
                <span>知识库为空</span>
              </div>
            )}
          </div>
        </section>

        <footer className="sidebar-footer">
          <div className={`readiness-dot ${serviceReady ? "ready" : "offline"}`} />
          <div>
            <strong>{serviceReady ? "服务就绪" : "服务未就绪"}</strong>
            <span>{providerLabel}</span>
          </div>
        </footer>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <h1>知识库问答</h1>
            <span>Dense retrieval · source-grounded generation</span>
          </div>
          <div className="header-actions">
            <div className="service-pills" aria-label="服务状态">
              <span className={activeComponents?.milvus === "ready" ? "healthy" : "unhealthy"}>
                <Database size={14} /> Milvus
              </span>
              <span className={activeComponents?.llm === "ready" ? "healthy" : "unhealthy"}>
                <Server size={14} /> LLM
              </span>
            </div>
            <button
              className="icon-button bordered"
              type="button"
              title={sourcesOpen ? "收起引用来源" : "展开引用来源"}
              aria-label={sourcesOpen ? "收起引用来源" : "展开引用来源"}
              onClick={() => setSourcesOpen((current) => !current)}
            >
              {sourcesOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
            </button>
          </div>
        </header>

        <div className={`content-grid ${sourcesOpen ? "with-sources" : ""}`}>
          <section className="chat-panel" aria-label="问答对话">
            <div className="message-list">
              {messages.map((message) => (
                <article key={message.id} className={`message message-${message.role}`}>
                  {message.role === "assistant" && (
                    <div className="assistant-avatar" aria-hidden="true"><Bot size={17} /></div>
                  )}
                  <div className="message-body">
                    {message.role === "assistant" && message.stage !== "done" && !message.content && (
                      <div className="message-progress">
                        <LoaderCircle className="spin" size={16} />
                        {message.stage === "retrieving" ? "正在检索知识库" : "正在生成回答"}
                      </div>
                    )}
                    {message.content && (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                    )}
                    {message.role === "assistant" && message.sources.length > 0 && (
                      <button
                        type="button"
                        className="citation-link"
                        onClick={() => {
                          setSelectedSources(message.sources);
                          setSourcesOpen(true);
                        }}
                      >
                        {message.sources.length} 条引用来源
                      </button>
                    )}
                  </div>
                </article>
              ))}
              <div ref={chatEnd} />
            </div>

            <form className="composer" onSubmit={submitQuestion}>
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="向知识库提问"
                rows={2}
                maxLength={4000}
                disabled={!serviceReady}
              />
              {isStreaming ? (
                <button className="send-button stop-button" type="button" onClick={stopStream} title="停止生成">
                  <Square size={16} fill="currentColor" />
                  停止
                </button>
              ) : (
                <button className="send-button" type="submit" disabled={!question.trim() || !serviceReady}>
                  <Send size={17} />
                  发送
                </button>
              )}
              <div className="composer-meta">
                <span>{config.data?.collection_name || "rag_documents"}</span>
                <span>{question.length}/4000</span>
              </div>
            </form>
          </section>

          {sourcesOpen && (
            <aside className="sources-panel">
              <header>
                <div>
                  <h2>引用来源</h2>
                  <span>{currentSourceCount ? `${currentSourceCount} 个检索片段` : "等待检索结果"}</span>
                </div>
              </header>
              <div className="sources-list">
                {selectedSources.map((source) => (
                  <SourceItem key={`${source.rank}-${source.chunk_id || source.source}`} source={source} />
                ))}
                {selectedSources.length === 0 && (
                  <div className="sources-empty">
                    <FileText size={26} />
                    <span>暂无引用</span>
                  </div>
                )}
              </div>
            </aside>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
