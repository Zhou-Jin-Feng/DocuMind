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
  Clock3,
  Database,
  FileText,
  GitBranch,
  LibraryBig,
  LoaderCircle,
  MessageSquarePlus,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Send,
  Server,
  Square,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  APIError,
  deleteDocument,
  getDocument,
  getDocuments,
  getPublicConfig,
  getReadiness,
  reindexDocument,
  streamChat,
  uploadDocument,
  type UploadProgress,
} from "./api";
import {
  createConversation,
  hasConversationContent,
  loadConversations,
  saveConversations,
  titleFromMessages,
  type ConversationRecord,
} from "./conversations";
import type {
  ChatEvent,
  ChatMessage,
  DocumentDetail,
  DocumentRecord,
  SourceReference,
} from "./types";

const QUERY_RETRY_COUNT = 2;
const configuredRefreshInterval = Number(
  import.meta.env.VITE_QUERY_REFRESH_INTERVAL_MS,
);
const QUERY_REFRESH_INTERVAL =
  Number.isFinite(configuredRefreshInterval) && configuredRefreshInterval >= 250
    ? configuredRefreshInterval
    : 30_000;

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

function fullDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "--";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(parsed);
}

function shortIdentifier(value?: string | null): string {
  return value ? value.slice(0, 12) : "--";
}

function updateMessage(
  messages: ChatMessage[],
  id: string,
  update: (message: ChatMessage) => ChatMessage,
): ChatMessage[] {
  return messages.map((message) => (message.id === id ? update(message) : message));
}

function latestSources(messages: ChatMessage[]): SourceReference[] {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].sources.length > 0) return messages[index].sources;
  }
  return [];
}

type ConversationState = {
  activeId: string;
  items: ConversationRecord[];
};

type ConversationAction =
  | { type: "clear-current" }
  | { type: "clear-history" }
  | { type: "delete"; conversationId: string }
  | null;

type UploadState = UploadProgress & {
  filename: string;
  fileSize: number;
};

function statusLabel(status: string): string {
  if (status === "active") return "已索引";
  if (status === "indexing") return "处理中";
  if (status === "failed") return "失败";
  if (status === "pending") return "等待中";
  if (status === "superseded") return "历史版本";
  if (status === "deleting") return "删除中";
  if (status === "deleted") return "已删除";
  return status;
}

function DocumentItem({
  document,
  onOpen,
}: {
  document: DocumentRecord;
  onOpen: () => void;
}) {
  return (
    <button
      className="document-item"
      type="button"
      aria-label={`查看文档 ${document.display_name}`}
      onClick={onOpen}
    >
      <div className="document-icon" aria-hidden="true">
        <FileText size={17} />
      </div>
      <div className="document-copy">
        <strong title={document.display_name}>{document.display_name}</strong>
        <span>
          {document.chunk_count} 个片段 · {formatBytes(document.file_size_bytes)} · {shortDate(document.updated_at)}
        </span>
      </div>
      <span className={`document-status status-${document.status}`}>
        {statusLabel(document.status)}
      </span>
    </button>
  );
}

type ManagementNotice = {
  kind: "success" | "error";
  message: string;
} | null;

type SidebarNotice = {
  kind: "success" | "error";
  message: string;
} | null;

function DocumentDetailsDialog({
  detail,
  loading,
  failed,
  reindexing,
  deleting,
  notice,
  onClose,
  onReindex,
  onDelete,
}: {
  detail?: DocumentDetail;
  loading: boolean;
  failed: boolean;
  reindexing: boolean;
  deleting: boolean;
  notice: ManagementNotice;
  onClose: () => void;
  onReindex: () => void;
  onDelete: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setConfirmDelete(false);
  }, [detail?.document_key]);

  return (
    <div className="dialog-backdrop">
      <section
        className="document-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-dialog-title"
      >
        <header className="dialog-header">
          <div>
            <span>文档详情</span>
            <h2 id="document-dialog-title">
              {detail?.display_name || "正在读取文档"}
            </h2>
          </div>
          <button
            className="icon-button bordered"
            type="button"
            title="关闭文档详情"
            aria-label="关闭文档详情"
            onClick={onClose}
            disabled={deleting}
          >
            <X size={18} />
          </button>
        </header>

        <div className="dialog-body">
          {loading && (
            <div className="dialog-state">
              <LoaderCircle className="spin" size={20} />
              正在加载文档详情
            </div>
          )}
          {failed && (
            <div className="dialog-state error-text">
              <CircleAlert size={20} />
              文档详情暂时不可用
            </div>
          )}
          {detail && (
            <>
              <div className="document-summary-row">
                <span className={`document-status status-${detail.status}`}>
                  {statusLabel(detail.status)}
                </span>
                <span>{detail.file_type?.replace(".", "").toUpperCase() || "未知格式"}</span>
              </div>

              <dl className="document-metadata">
                <div>
                  <dt><GitBranch size={14} />文档版本</dt>
                  <dd>{detail.version_count} 个版本</dd>
                </div>
                <div>
                  <dt><FileText size={14} />索引内容</dt>
                  <dd>{detail.chunk_count} 个片段 · {formatBytes(detail.file_size_bytes)}</dd>
                </div>
                <div>
                  <dt><Clock3 size={14} />最近更新</dt>
                  <dd>{fullDate(detail.updated_at)}</dd>
                </div>
                <div>
                  <dt><Database size={14} />活动版本</dt>
                  <dd className="monospace">{shortIdentifier(detail.active_version_id)}</dd>
                </div>
              </dl>

              {detail.error_type && (
                <div className="document-failure">
                  <CircleAlert size={17} />
                  <div>
                    <strong>最近一次索引失败</strong>
                    <span>{detail.error_type}</span>
                  </div>
                </div>
              )}

              {notice && (
                <div className={`management-notice notice-${notice.kind}`}>
                  {notice.kind === "success" ? <Check size={16} /> : <CircleAlert size={16} />}
                  <span>{notice.message}</span>
                </div>
              )}

              <div className="document-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={onReindex}
                  disabled={reindexing || deleting || detail.status === "indexing"}
                >
                  {reindexing ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
                  {reindexing ? "正在重建" : "重新建立索引"}
                </button>
                <button
                  className="danger-button"
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  disabled={reindexing || deleting || detail.status === "indexing"}
                >
                  <Trash2 size={16} />
                  删除文档
                </button>
              </div>

              {confirmDelete && (
                <div className="delete-confirmation">
                  <div>
                    <strong>删除文档及全部向量索引？</strong>
                    <span>此操作不可撤销。</span>
                  </div>
                  <div>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => setConfirmDelete(false)}
                      disabled={deleting}
                    >
                      取消
                    </button>
                    <button
                      type="button"
                      className="danger-button compact"
                      onClick={onDelete}
                      disabled={deleting}
                    >
                      {deleting ? <LoaderCircle className="spin" size={15} /> : <Trash2 size={15} />}
                      {deleting ? "正在删除" : "确认删除"}
                    </button>
                  </div>
                </div>
              )}

              <section className="index-history" aria-labelledby="index-history-title">
                <header>
                  <h3 id="index-history-title">索引历史</h3>
                  <span>{detail.indexes.length} 条记录</span>
                </header>
                <div className="index-history-list">
                  {detail.indexes.map((index) => (
                    <article className="index-history-item" key={index.index_id}>
                      <div className="index-history-heading">
                        <div>
                          <strong>版本 {index.version_number}</strong>
                          {index.is_active && <span className="active-marker">当前</span>}
                        </div>
                        <span className={`document-status status-${index.status}`}>
                          {statusLabel(index.status)}
                        </span>
                      </div>
                      <div className="index-history-meta">
                        <span>{index.chunk_count} 个片段</span>
                        <span>{fullDate(index.updated_at)}</span>
                        <span className="monospace">{shortIdentifier(index.document_version_id)}</span>
                      </div>
                      {index.error_type && (
                        <p className="index-error">失败原因：{index.error_type}</p>
                      )}
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function ConversationHistory({
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

function UploadProgressPanel({ progress }: { progress: UploadState }) {
  const indexing = progress.phase === "indexing";
  return (
    <div className="upload-progress" role="status" aria-live="polite">
      <div className="upload-progress-heading">
        <FileText size={15} />
        <span>
          <strong title={progress.filename}>{progress.filename}</strong>
          <small>{formatBytes(progress.fileSize)}</small>
        </span>
      </div>
      <div
        className={`upload-progress-track ${indexing ? "indexing" : ""}`}
        aria-label={indexing ? "正在建立向量索引" : `文件上传进度 ${progress.percent}%`}
      >
        <span style={{ width: `${Math.max(progress.percent, 4)}%` }} />
      </div>
      <div className="upload-stages">
        <span className={indexing ? "complete" : "active"}>
          {indexing ? <Check size={13} /> : <LoaderCircle className="spin" size={13} />}
          上传文件{indexing ? "完成" : ` ${progress.percent}%`}
        </span>
        <span className={indexing ? "active" : "pending"}>
          {indexing ? <LoaderCircle className="spin" size={13} /> : <Clock3 size={13} />}
          解析、切分与向量化
        </span>
      </div>
    </div>
  );
}

function ConfirmationDialog({
  title,
  description,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="dialog-backdrop conversation-confirm-backdrop">
      <section
        className="conversation-confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="conversation-confirm-title"
      >
        <div className="confirmation-icon" aria-hidden="true">
          <Trash2 size={20} />
        </div>
        <div>
          <h2 id="conversation-confirm-title">{title}</h2>
          <p>{description}</p>
        </div>
        <div className="confirmation-actions">
          <button className="secondary-button" type="button" onClick={onCancel}>
            取消
          </button>
          <button className="danger-button" type="button" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

function SourceItem({ source }: { source: SourceReference }) {
  const metrics = [
    source.distance != null ? `距离 ${source.distance.toFixed(4)}` : null,
    source.rerank_score != null ? `重排 ${source.rerank_score.toFixed(4)}` : null,
    source.fusion_score != null ? `融合 ${source.fusion_score.toFixed(5)}` : null,
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
  const [conversationState, setConversationState] = useState<ConversationState>(() => {
    const saved = loadConversations(window.localStorage);
    const active = saved[0] ?? createConversation();
    return {
      activeId: active.id,
      items: saved.length > 0 ? saved : [active],
    };
  });
  const [question, setQuestion] = useState("");
  const [activeAnswerId, setActiveAnswerId] = useState<string | null>(null);
  const [selectedSources, setSelectedSources] = useState<SourceReference[]>([]);
  const [sourcesOpen, setSourcesOpen] = useState(
    () => !window.matchMedia("(max-width: 860px)").matches,
  );
  const [uploadNotice, setUploadNotice] = useState<SidebarNotice>(null);
  const [uploadProgress, setUploadProgress] = useState<UploadState | null>(null);
  const [selectedDocumentKey, setSelectedDocumentKey] = useState<string | null>(null);
  const [managementNotice, setManagementNotice] = useState<ManagementNotice>(null);
  const [conversationAction, setConversationAction] = useState<ConversationAction>(null);
  const streamController = useRef<AbortController | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const chatEnd = useRef<HTMLDivElement | null>(null);

  const activeConversation =
    conversationState.items.find((item) => item.id === conversationState.activeId) ??
    conversationState.items[0];
  const messages = activeConversation?.messages ?? [];

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
  const documentDetail = useQuery({
    queryKey: ["document", selectedDocumentKey],
    queryFn: () => getDocument(selectedDocumentKey as string),
    enabled: selectedDocumentKey !== null,
    retry: QUERY_RETRY_COUNT,
    refetchInterval: QUERY_REFRESH_INTERVAL,
  });
  const upload = useMutation({
    mutationFn: (file: File) =>
      uploadDocument(file, (progress) => {
        setUploadProgress({ ...progress, filename: file.name, fileSize: file.size });
      }),
    onMutate: (file) => {
      setUploadProgress({
        phase: "uploading",
        loaded: 0,
        total: file.size,
        percent: 0,
        filename: file.name,
        fileSize: file.size,
      });
    },
    onSuccess: (result) => {
      setUploadNotice({
        kind: "success",
        message:
          result.status === "noop"
            ? "文档已存在，索引保持不变。"
            : `索引完成，共生成 ${result.chunk_count} 个片段。`,
      });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (error) => {
      setUploadNotice({
        kind: "error",
        message: error instanceof Error ? error.message : "文档上传失败。",
      });
    },
    onSettled: () => setUploadProgress(null),
  });
  const reindex = useMutation({
    mutationFn: reindexDocument,
    onMutate: () => setManagementNotice(null),
    onSuccess: (result, documentKey) => {
      setManagementNotice({
        kind: "success",
        message: `索引重建完成，共生成 ${result.chunk_count} 个片段。`,
      });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["document", documentKey] });
    },
    onError: (error) => {
      setManagementNotice({
        kind: "error",
        message: error instanceof Error ? error.message : "索引重建失败。",
      });
    },
  });
  const removeDocument = useMutation({
    mutationFn: deleteDocument,
    onMutate: () => setManagementNotice(null),
    onSuccess: (result) => {
      setSelectedDocumentKey(null);
      setManagementNotice(null);
      setUploadNotice({
        kind: "success",
        message: result.cleanup_pending
          ? "文档已删除，但部分源文件仍待清理。"
          : "文档及向量索引已删除。",
      });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.removeQueries({ queryKey: ["document", result.document_key] });
    },
    onError: (error) => {
      setManagementNotice({
        kind: "error",
        message: error instanceof Error ? error.message : "文档删除失败。",
      });
    },
  });

  const isStreaming = activeAnswerId !== null;
  const activeComponents = readiness.data?.components;
  const serviceReady = readiness.data?.ready === true;
  const currentSourceCount = selectedSources.length;
  const documentsTotal = documents.data?.total ?? 0;
  const serviceChecking = readiness.isLoading && !readiness.data;
  const serviceStatusLabel = serviceChecking
    ? "正在检查服务"
    : serviceReady
      ? "服务就绪"
      : "服务未就绪";
  const actionConversation =
    conversationAction?.type === "delete"
      ? conversationState.items.find(
          (item) => item.id === conversationAction.conversationId,
        )
      : undefined;
  const conversationActionCopy =
    conversationAction?.type === "clear-history"
      ? {
          title: "清空全部对话历史？",
          description: "本机保存的全部问答记录将被删除，此操作不可撤销。",
          confirmLabel: "清空历史",
        }
      : conversationAction?.type === "delete"
        ? {
            title: "删除这条对话？",
            description: `“${actionConversation?.title || "未命名对话"}”将从本机历史中删除。`,
            confirmLabel: "删除对话",
          }
        : {
            title: "清空当前对话？",
            description: "当前问答内容将被清除，此操作不可撤销。",
            confirmLabel: "清空对话",
          };

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    if (!isStreaming) {
      saveConversations(window.localStorage, conversationState.items);
    }
  }, [conversationState.items, isStreaming]);

  useEffect(() => {
    return () => streamController.current?.abort();
  }, []);

  useEffect(() => {
    if (!selectedDocumentKey) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !removeDocument.isPending) {
        setSelectedDocumentKey(null);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedDocumentKey, removeDocument.isPending]);

  useEffect(() => {
    if (!conversationAction) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setConversationAction(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [conversationAction]);

  const providerLabel = useMemo(() => {
    if (config.isError) return "配置不可用";
    if (!config.data) return "配置加载中";
    return `${config.data.embedding_provider} · ${config.data.llm_provider}`;
  }, [config.data, config.isError]);

  function setMessages(
    update: ChatMessage[] | ((current: ChatMessage[]) => ChatMessage[]),
  ) {
    setConversationState((current) => ({
      ...current,
      items: current.items.map((conversation) => {
        if (conversation.id !== current.activeId) return conversation;
        const nextMessages =
          typeof update === "function" ? update(conversation.messages) : update;
        return {
          ...conversation,
          messages: nextMessages,
          title: titleFromMessages(nextMessages),
          updatedAt: new Date().toISOString(),
        };
      }),
    }));
  }

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

  function startNewConversation() {
    streamController.current?.abort();
    setActiveAnswerId(null);
    setConversationState((current) => {
      const active = current.items.find((item) => item.id === current.activeId);
      if (active && !hasConversationContent(active)) {
        return {
          ...current,
          items: current.items.map((item) =>
            item.id === current.activeId
              ? { ...item, messages: [], title: "新对话", updatedAt: new Date().toISOString() }
              : item,
          ),
        };
      }
      const conversation = createConversation();
      return {
        activeId: conversation.id,
        items: [conversation, ...current.items],
      };
    });
    setSelectedSources([]);
    setQuestion("");
  }

  function selectConversation(conversation: ConversationRecord) {
    if (conversation.id === conversationState.activeId) return;
    streamController.current?.abort();
    setActiveAnswerId(null);
    setConversationState((current) => ({ ...current, activeId: conversation.id }));
    setSelectedSources(latestSources(conversation.messages));
    setQuestion("");
  }

  function deleteConversation(conversationId: string) {
    const remaining = conversationState.items.filter((item) => item.id !== conversationId);
    const fallback = remaining[0] ?? createConversation();
    const deletingActive = conversationState.activeId === conversationId;
    setConversationState({
      activeId: deletingActive ? fallback.id : conversationState.activeId,
      items: remaining.length > 0 ? remaining : [fallback],
    });
    if (deletingActive) {
      streamController.current?.abort();
      setActiveAnswerId(null);
      setSelectedSources(latestSources(fallback.messages));
      setQuestion("");
    }
  }

  function confirmConversationAction() {
    if (!conversationAction) return;
    if (conversationAction.type === "clear-current") {
      streamController.current?.abort();
      setActiveAnswerId(null);
      setMessages([]);
      setSelectedSources([]);
      setQuestion("");
    } else if (conversationAction.type === "clear-history") {
      const conversation = createConversation();
      streamController.current?.abort();
      setActiveAnswerId(null);
      setConversationState({ activeId: conversation.id, items: [conversation] });
      setSelectedSources([]);
      setQuestion("");
    } else {
      deleteConversation(conversationAction.conversationId);
    }
    setConversationAction(null);
  }

  function handleFileSelected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadNotice(null);
    upload.mutate(file);
    event.target.value = "";
  }

  function openDocument(documentKey: string) {
    setManagementNotice(null);
    setSelectedDocumentKey(documentKey);
  }

  return (
    <>
      <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <LibraryBig size={21} />
          </div>
          <div>
            <strong>RAG Workbench</strong>
            <span>知识库工作台</span>
          </div>
        </div>

        <button className="new-chat-button" type="button" onClick={startNewConversation}>
          <MessageSquarePlus size={17} />
          新建对话
        </button>

        <ConversationHistory
          conversations={conversationState.items}
          activeId={conversationState.activeId}
          onSelect={selectConversation}
          onDelete={(conversationId) =>
            setConversationAction({ type: "delete", conversationId })
          }
          onClear={() => setConversationAction({ type: "clear-history" })}
        />

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
            title={!serviceReady ? "文档服务就绪后可上传" : "上传文档"}
          >
            {upload.isPending ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}
            {upload.isPending ? "正在处理文档" : "上传文档"}
          </button>
          {uploadProgress && <UploadProgressPanel progress={uploadProgress} />}
          {uploadNotice && (
            <div className={`upload-notice ${uploadNotice.kind === "error" ? "notice-error" : ""}`}>
              {uploadNotice.kind === "error" ? <CircleAlert size={15} /> : <Check size={15} />}
              <span>{uploadNotice.message}</span>
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
            {documents.isLoading && !documents.data ? (
              <div className="list-placeholder">
                <LoaderCircle className="spin" size={18} />
                正在读取文档
              </div>
            ) : documents.isError ? (
              <div className="list-error-state">
                <CircleAlert size={20} />
                <strong>文档服务不可用</strong>
                <button type="button" onClick={() => void documents.refetch()}>
                  <RefreshCw size={13} />重新加载
                </button>
              </div>
            ) : (
              <>
                {documents.data?.items.map((document) => (
                  <DocumentItem
                    key={document.document_key}
                    document={document}
                    onOpen={() => openDocument(document.document_key)}
                  />
                ))}
                {documents.data?.total === 0 && (
                  <div className="empty-documents">
                    <Database size={22} />
                    <strong>知识库为空</strong>
                    <span>尚未上传文档</span>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <footer className="sidebar-footer">
          <div className={`readiness-dot ${serviceReady ? "ready" : "offline"}`} />
          <div>
            <strong>{serviceStatusLabel}</strong>
            <span>{providerLabel}</span>
          </div>
        </footer>
      </aside>

      <main className="workspace">
        <header className="workspace-header">
          <div>
            <h1>知识库问答</h1>
            <span>{activeConversation?.title || "新对话"}</span>
          </div>
          <div className="header-actions">
            <div className="service-pills" aria-label="服务状态">
              <span className={activeComponents?.milvus === "ready" ? "healthy" : "unhealthy"}>
                <Database size={14} /> Milvus
              </span>
              <span className={activeComponents?.llm === "ready" ? "healthy" : "unhealthy"}>
                <Server size={14} /> 语言模型
              </span>
            </div>
            <button
              className="icon-button bordered"
              type="button"
              title="清空当前对话"
              aria-label="清空当前对话"
              onClick={() => setConversationAction({ type: "clear-current" })}
              disabled={messages.length === 0}
            >
              <Trash2 size={17} />
            </button>
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
            {(serviceChecking || !serviceReady || config.isError) && (
              <div
                className={`service-alert ${serviceChecking ? "checking" : "error"}`}
                role="status"
              >
                {serviceChecking ? (
                  <LoaderCircle className="spin" size={18} />
                ) : (
                  <CircleAlert size={18} />
                )}
                <div>
                  <strong>{serviceChecking ? "正在连接后端服务" : "问答服务未就绪"}</strong>
                  <span>
                    {serviceChecking
                      ? "正在读取运行状态与公开配置"
                      : readiness.isError
                        ? "无法连接后端，请确认 FastAPI 服务已经启动。"
                        : "Milvus、嵌入模型或语言模型仍有依赖未就绪。"}
                  </span>
                </div>
                {!serviceChecking && (
                  <button
                    className="secondary-button compact"
                    type="button"
                    onClick={() => {
                      void readiness.refetch();
                      void config.refetch();
                      void documents.refetch();
                    }}
                  >
                    <RefreshCw size={14} />重新检查
                  </button>
                )}
              </div>
            )}
            <div className="message-list">
              {messages.length === 0 && (
                <div className="chat-empty">
                  <div aria-hidden="true"><Bot size={22} /></div>
                  <strong>暂无对话</strong>
                  <span>
                    {documentsTotal > 0
                      ? `知识库中有 ${documentsTotal} 个文档`
                      : "知识库暂无文档"}
                  </span>
                </div>
              )}
              {messages.map((message) => (
                <article key={message.id} className={`message message-${message.role}`}>
                  {message.role === "assistant" && (
                    <div className="assistant-avatar" aria-hidden="true"><Bot size={17} /></div>
                  )}
                  <div className={`message-body ${message.stage === "error" ? "message-error" : ""}`}>
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
            <button
              className="sources-backdrop"
              type="button"
              aria-hidden="true"
              tabIndex={-1}
              onClick={() => setSourcesOpen(false)}
            />
          )}
          {sourcesOpen && (
            <aside className="sources-panel" aria-label="引用来源">
              <header>
                <div>
                  <h2>引用来源</h2>
                  <span>{currentSourceCount ? `${currentSourceCount} 个检索片段` : "等待检索结果"}</span>
                </div>
                <button
                  className="icon-button bordered sources-close"
                  type="button"
                  title="关闭引用来源"
                  aria-label="关闭引用来源"
                  onClick={() => setSourcesOpen(false)}
                >
                  <X size={16} />
                </button>
              </header>
              <div className="sources-list">
                {selectedSources.map((source) => (
                  <SourceItem key={`${source.rank}-${source.chunk_id || source.source}`} source={source} />
                ))}
                {selectedSources.length === 0 && (
                  <div className="sources-empty">
                    <FileText size={26} />
                    <strong>暂无引用来源</strong>
                    <span>当前对话还没有检索结果</span>
                  </div>
                )}
              </div>
            </aside>
          )}
        </div>
      </main>
      </div>
      {selectedDocumentKey && (
        <DocumentDetailsDialog
          detail={documentDetail.data}
          loading={documentDetail.isLoading}
          failed={documentDetail.isError}
          reindexing={reindex.isPending}
          deleting={removeDocument.isPending}
          notice={managementNotice}
          onClose={() => setSelectedDocumentKey(null)}
          onReindex={() => reindex.mutate(selectedDocumentKey)}
          onDelete={() => removeDocument.mutate(selectedDocumentKey)}
        />
      )}
      {conversationAction && (
        <ConfirmationDialog
          title={conversationActionCopy.title}
          description={conversationActionCopy.description}
          confirmLabel={conversationActionCopy.confirmLabel}
          onCancel={() => setConversationAction(null)}
          onConfirm={confirmConversationAction}
        />
      )}
    </>
  );
}

export default App;
