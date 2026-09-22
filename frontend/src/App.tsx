import {
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CircleAlert,
  Database,
  LibraryBig,
  LoaderCircle,
  MessageSquarePlus,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Server,
  Trash2,
  Upload,
} from "lucide-react";
import {
  deleteDocument,
  getDocument,
  getDocuments,
  getPublicConfig,
  getReadiness,
  reindexDocument,
  streamChat,
  uploadDocument,
} from "./api";
import {
  createConversation,
  loadConversations,
  saveConversations,
  type ConversationRecord,
} from "./conversations";
import { Composer } from "./components/Composer";
import { ConfirmationDialog as ConfirmationDialogView } from "./components/ConfirmationDialog";
import { ConversationHistory as ConversationHistoryView } from "./components/ConversationHistory";
import {
  DocumentDetailsDialog as DocumentDetailsDialogView,
  DocumentItem as DocumentItemView,
  UploadProgressPanel as UploadProgressPanelView,
  type ManagementNotice,
  type UploadState,
} from "./components/Documents";
import { MessageList } from "./components/MessageList";
import { Notice } from "./components/Notice";
import { SourcesPanel } from "./components/SourcesPanel";
import {
  recordFe01AppRender,
  recordFe01TokenBatch,
  recordFe01TokenReceived,
} from "./fe01Metrics";
import {
  conversationReducer,
  type AnswerTarget,
  type ConversationState,
} from "./features/chat/conversationState";
import {
  createChatStreamController,
  type ChatRunIdentity,
} from "./features/chat/streamController";

const QUERY_RETRY_COUNT = 2;
const configuredRefreshInterval = Number(
  import.meta.env.VITE_QUERY_REFRESH_INTERVAL_MS,
);
const QUERY_REFRESH_INTERVAL =
  Number.isFinite(configuredRefreshInterval) && configuredRefreshInterval >= 250
    ? configuredRefreshInterval
    : 30_000;
const FE01_PROFILE_ENABLED = import.meta.env.VITE_FE01_PROFILE === "1";

type ConversationAction =
  | { type: "clear-current" }
  | { type: "clear-history" }
  | { type: "delete"; conversationId: string }
  | null;

type SidebarNotice = {
  kind: "success" | "error";
  message: string;
} | null;

function createInitialConversationState(): ConversationState {
  const saved = loadConversations(window.localStorage);
  const active = saved[0] ?? createConversation();
  return {
    activeId: active.id,
    items: saved.length > 0 ? saved : [active],
  };
}

function latestSourceTarget(
  conversation?: ConversationRecord,
): AnswerTarget | null {
  if (!conversation) return null;
  for (let index = conversation.messages.length - 1; index >= 0; index -= 1) {
    const message = conversation.messages[index];
    if (message.role === "assistant" && message.sources.length > 0) {
      return { conversationId: conversation.id, answerId: message.id };
    }
  }
  return null;
}

function App() {
  if (FE01_PROFILE_ENABLED) recordFe01AppRender();
  const queryClient = useQueryClient();
  const [conversationState, dispatchConversation] = useReducer(
    conversationReducer,
    undefined,
    createInitialConversationState,
  );
  const [question, setQuestion] = useState("");
  const [activeRun, setActiveRun] = useState<ChatRunIdentity | null>(null);
  const [selectedSourceTarget, setSelectedSourceTarget] =
    useState<AnswerTarget | null>(null);
 const [selectedSourceRank, setSelectedSourceRank] = useState<number | null>(null);
  const [sourceHighlightRequestId, setSourceHighlightRequestId] = useState(0);
  const [sourcesOpen, setSourcesOpen] = useState(
    () => !window.matchMedia("(max-width: 860px)").matches,
  );
  const [uploadNotice, setUploadNotice] = useState<SidebarNotice>(null);
  const [uploadProgress, setUploadProgress] = useState<UploadState | null>(null);
  const [selectedDocumentKey, setSelectedDocumentKey] = useState<string | null>(null);
  const [managementNotice, setManagementNotice] = useState<ManagementNotice>(null);
  const [conversationAction, setConversationAction] = useState<ConversationAction>(null);
  const chatController = useRef<
    ReturnType<typeof createChatStreamController> | null
  >(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const uploadButtonRef = useRef<HTMLButtonElement | null>(null);
  const newChatButtonRef = useRef<HTMLButtonElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const documentListRef = useRef<HTMLDivElement | null>(null);
  const sourcesToggleRef = useRef<HTMLButtonElement | null>(null);
  const selectPrompt = useCallback((prompt: string) => {
    setQuestion(prompt);
    window.requestAnimationFrame(() => composerRef.current?.focus());
  }, []);

  const activeConversation =
    conversationState.items.find((item) => item.id === conversationState.activeId) ??
    conversationState.items[0];
  const messages = activeConversation?.messages ?? [];
  const selectedSources = useMemo(() => {
    if (
      !selectedSourceTarget ||
      selectedSourceTarget.conversationId !== conversationState.activeId
    ) {
      return [];
    }
    const conversation = conversationState.items.find(
      (item) => item.id === selectedSourceTarget.conversationId,
    );
    return (
      conversation?.messages.find(
        (message) => message.id === selectedSourceTarget.answerId,
      )?.sources ?? []
    );
  }, [conversationState.activeId, conversationState.items, selectedSourceTarget]);

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

  const isStreaming = activeRun !== null;
  const activeComponents = readiness.data?.components;
  const serviceReady = readiness.data?.ready === true;
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
    if (!isStreaming) {
      saveConversations(window.localStorage, conversationState.items);
    }
  }, [conversationState.items, isStreaming]);

 useEffect(() => {
   setSelectedSourceTarget(latestSourceTarget(activeConversation));
    setSelectedSourceRank(null);
 }, [activeConversation?.id]);

  useEffect(() => {
    const controller = createChatStreamController({
      transport: streamChat,
      onUpdate: (target, update) => {
        dispatchConversation({
          type: "answer/update",
          target,
          update,
          at: new Date().toISOString(),
        });
      },
      onActiveChange: setActiveRun,
      onTokenReceived: recordFe01TokenReceived,
      onTokenBatch: recordFe01TokenBatch,
    });
    chatController.current = controller;

    return () => {
      controller.dispose();
      if (chatController.current === controller) {
        chatController.current = null;
      }
    };
  }, []);

  const providerLabel = useMemo(() => {
    if (config.isError) return "配置不可用";
    if (!config.data) return "配置加载中";
    return `${config.data.embedding_provider} · ${config.data.llm_provider}`;
  }, [config.data, config.isError]);

  const openSources = useCallback(
    (answerId: string, sourceRank?: number) => {
      setSelectedSourceTarget({
        conversationId: conversationState.activeId,
        answerId,
      });
     setSelectedSourceRank(sourceRank ?? null);
      setSourceHighlightRequestId((value) => value + 1);
     setSourcesOpen(true);
    },
    [conversationState.activeId],
  );

  function submitQuestion(event?: FormEvent) {
    event?.preventDefault();
    const normalized = question.trim();
    if (!normalized || isStreaming || !activeConversation) return;

    const userId = crypto.randomUUID();
    const answerId = crypto.randomUUID();
    const identity: ChatRunIdentity = {
      requestId: crypto.randomUUID(),
      conversationId: activeConversation.id,
      answerId,
    };
   setQuestion("");
    setSelectedSourceRank(null);
   setSelectedSourceTarget({
      conversationId: identity.conversationId,
      answerId,
    });
    dispatchConversation({
      type: "turn/start",
      conversationId: identity.conversationId,
      userId,
      answerId,
      question: normalized,
      at: new Date().toISOString(),
    });
    chatController.current?.start({ identity, question: normalized });
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitQuestion();
    }
  }

  function stopStream() {
    chatController.current?.stop();
  }

  function startNewConversation() {
    chatController.current?.stop();
    const conversation = createConversation();
    dispatchConversation({
      type: "conversation/new",
      conversation,
    });
   setSelectedSourceTarget(null);
    setSelectedSourceRank(null);
   setQuestion("");
  }

  function selectConversation(conversation: ConversationRecord) {
    if (conversation.id === conversationState.activeId) return;
    chatController.current?.stop();
    dispatchConversation({
      type: "conversation/select",
      conversationId: conversation.id,
    });
   setSelectedSourceTarget(latestSourceTarget(conversation));
    setSelectedSourceRank(null);
   setQuestion("");
  }

  function deleteConversation(conversationId: string) {
    const deletingActive = conversationState.activeId === conversationId;
    if (deletingActive) chatController.current?.stop();
    dispatchConversation({
      type: "conversation/delete",
      conversationId,
      fallback: createConversation(),
    });
    if (deletingActive) {
     setSelectedSourceTarget(null);
      setSelectedSourceRank(null);
     setQuestion("");
    }
  }

  function confirmConversationAction() {
    if (!conversationAction) return;
    if (conversationAction.type === "clear-current") {
      chatController.current?.stop();
      dispatchConversation({
        type: "conversation/clear",
        conversationId: conversationState.activeId,
        at: new Date().toISOString(),
      });
     setSelectedSourceTarget(null);
      setSelectedSourceRank(null);
     setQuestion("");
    } else if (conversationAction.type === "clear-history") {
      const conversation = createConversation();
      chatController.current?.stop();
      dispatchConversation({
        type: "conversation/clear-all",
        fallback: conversation,
      });
      setSelectedSourceTarget(null);
      setSelectedSourceRank(null);
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

        <button
          ref={newChatButtonRef}
          className="new-chat-button"
          type="button"
          onClick={startNewConversation}
        >
          <MessageSquarePlus size={17} />
          新建对话
        </button>

        <ConversationHistoryView
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
            ref={uploadButtonRef}
            className="upload-button"
            type="button"
            onClick={() => fileInput.current?.click()}
            disabled={upload.isPending || !serviceReady}
            title={!serviceReady ? "文档服务就绪后可上传" : "上传文档"}
          >
            {upload.isPending ? <LoaderCircle className="spin" size={17} /> : <Upload size={17} />}
            {upload.isPending ? "正在处理文档" : "上传文档"}
          </button>
          {uploadProgress && <UploadProgressPanelView progress={uploadProgress} />}
          {uploadNotice && (
            <Notice
              kind={uploadNotice.kind}
              placement="sidebar"
              onDismiss={() => {
                setUploadNotice(null);
                queueMicrotask(() => {
                  const target = serviceReady
                    ? uploadButtonRef.current
                    : newChatButtonRef.current;
                  target?.focus({ preventScroll: true });
                });
              }}
            >
              {uploadNotice.message}
            </Notice>
          )}

          <div
            ref={documentListRef}
            className="document-list"
            aria-label="知识库文档"
            tabIndex={-1}
          >
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
                  <DocumentItemView
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
              ref={sourcesToggleRef}
              className="icon-button bordered"
              type="button"
              title={sourcesOpen ? "收起引用来源" : "展开引用来源"}
              aria-label={sourcesOpen ? "收起引用来源" : "展开引用来源"}
              onClick={() => {
                setSelectedSourceRank(null);
                setSourcesOpen((current) => !current);
              }}
            >
              {sourcesOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
            </button>
          </div>
        </header>

        <div className={`content-grid ${sourcesOpen ? "with-sources" : ""}`}>
          <section className="chat-panel" aria-label="问答对话">
            {(serviceChecking || !serviceReady || config.isError) && (
              <Notice
                kind={serviceChecking ? "warning" : "error"}
                placement="banner"
                title={serviceChecking ? "正在连接后端服务" : "问答服务未就绪"}
                icon={
                  serviceChecking ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <CircleAlert size={18} />
                  )
                }
                action={
                  !serviceChecking ? (
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
                  ) : undefined
                }
              >
                {serviceChecking
                  ? "正在读取运行状态与公开配置"
                  : readiness.isError
                    ? "无法连接后端，请确认 FastAPI 服务已经启动。"
                    : "Milvus、嵌入模型或语言模型仍有依赖未就绪。"}
              </Notice>
            )}
            <MessageList
              messages={messages}
              documentCount={documentsTotal}
              conversationId={conversationState.activeId}
              onOpenSources={openSources}
              onPromptSelect={selectPrompt}
            />

            <Composer
              question={question}
              serviceReady={serviceReady}
              streaming={isStreaming}
              collectionName={config.data?.collection_name || "rag_documents"}
              textareaRef={composerRef}
              onQuestionChange={setQuestion}
              onKeyDown={handleComposerKeyDown}
              onSubmit={submitQuestion}
              onStop={stopStream}
            />
          </section>

          <SourcesPanel
            open={sourcesOpen}
            sources={selectedSources}
           highlightedRank={selectedSourceRank}
            highlightRequestId={sourceHighlightRequestId}
            fallbackFocusRef={sourcesToggleRef}
            onOpenChange={setSourcesOpen}
          />
        </div>
      </main>
      </div>
      {selectedDocumentKey && (
        <DocumentDetailsDialogView
          detail={documentDetail.data}
          loading={documentDetail.isLoading}
          failed={documentDetail.isError}
          reindexing={reindex.isPending}
          deleting={removeDocument.isPending}
          notice={managementNotice}
          fallbackFocusRef={documentListRef}
          onClose={() => setSelectedDocumentKey(null)}
          onReindex={() => reindex.mutate(selectedDocumentKey)}
          onDelete={() => removeDocument.mutate(selectedDocumentKey)}
        />
      )}
      {conversationAction && (
        <ConfirmationDialogView
          title={conversationActionCopy.title}
          description={conversationActionCopy.description}
          confirmLabel={conversationActionCopy.confirmLabel}
          fallbackFocusRef={
            conversationAction.type === "clear-current" && serviceReady
              ? composerRef
              : newChatButtonRef
          }
          onCancel={() => setConversationAction(null)}
          onConfirm={confirmConversationAction}
        />
      )}
    </>
  );
}

export default App;
