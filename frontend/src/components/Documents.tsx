import {
  type RefObject,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  Check,
  CircleAlert,
  Clock3,
  Database,
  FileText,
  GitBranch,
  LoaderCircle,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import type { UploadProgress } from "../api";
import type { DocumentDetail, DocumentRecord } from "../types";
import { ConfirmationDialog } from "./ConfirmationDialog";
import { Modal, ModalDescription, ModalTitle } from "./Modal";
import { Notice } from "./Notice";

export type ManagementNotice = {
  kind: "success" | "error";
  message: string;
} | null;

export type UploadState = UploadProgress & {
  filename: string;
  fileSize: number;
};

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

export function DocumentItem({
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
          {document.chunk_count} 个片段 · {formatBytes(document.file_size_bytes)} ·{" "}
          {shortDate(document.updated_at)}
        </span>
      </div>
      <span className={`document-status status-${document.status}`}>
        {statusLabel(document.status)}
      </span>
    </button>
  );
}

export function DocumentDetailsDialog({
  detail,
  loading,
  failed,
  reindexing,
  deleting,
  notice,
  fallbackFocusRef,
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
  fallbackFocusRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  onReindex: () => void;
  onDelete: () => void;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const deleteButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    setConfirmDelete(false);
  }, [detail?.document_key]);

  useLayoutEffect(() => {
    if (notice?.kind === "error") setConfirmDelete(false);
  }, [notice]);

  return (
    <Modal
      variant="document"
      initialFocusRef={closeButtonRef}
      fallbackFocusRef={fallbackFocusRef}
      restoreFocus={deleting ? "fallback" : "trigger"}
      dismissible={!deleting && !confirmDelete}
      onDismiss={onClose}
    >
        <header className="dialog-header">
          <div>
            <span>文档详情</span>
            <ModalTitle>{detail?.display_name || "正在读取文档"}</ModalTitle>
            <ModalDescription className="visually-hidden">
              查看文档状态、元数据、索引历史和管理操作。
            </ModalDescription>
          </div>
          <button
            ref={closeButtonRef}
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
                  <dt>
                    <GitBranch size={14} />文档版本
                  </dt>
                  <dd>{detail.version_count} 个版本</dd>
                </div>
                <div>
                  <dt>
                    <FileText size={14} />索引内容
                  </dt>
                  <dd>
                    {detail.chunk_count} 个片段 · {formatBytes(detail.file_size_bytes)}
                  </dd>
                </div>
                <div>
                  <dt>
                    <Clock3 size={14} />最近更新
                  </dt>
                  <dd>{fullDate(detail.updated_at)}</dd>
                </div>
                <div>
                  <dt>
                    <Database size={14} />活动版本
                  </dt>
                  <dd className="monospace">{shortIdentifier(detail.active_version_id)}</dd>
                </div>
              </dl>

              {detail.error_type && (
                <Notice
                  kind="error"
                  placement="inline"
                  title="最近一次索引失败"
                  announce="off"
                >
                  <span className="monospace">{detail.error_type}</span>
                </Notice>
              )}

              {notice && (
                <Notice kind={notice.kind} placement="inline">
                  {notice.message}
                </Notice>
              )}

              <div className="document-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={onReindex}
                  disabled={reindexing || deleting || detail.status === "indexing"}
                >
                  {reindexing ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <RefreshCw size={16} />
                  )}
                  {reindexing ? "正在重建" : "重新建立索引"}
                </button>
                <button
                  ref={deleteButtonRef}
                  className="danger-button"
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  disabled={reindexing || deleting || detail.status === "indexing"}
                >
                  <Trash2 size={16} />
                  删除文档
                </button>
              </div>

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
                        <span className="monospace">
                          {shortIdentifier(index.document_version_id)}
                        </span>
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
      {confirmDelete && (
        <ConfirmationDialog
          title="删除文档及全部向量索引？"
          description="此操作不可撤销。"
          confirmLabel="确认删除"
          pendingLabel="正在删除"
          pending={deleting}
          fallbackFocusRef={deleteButtonRef}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={onDelete}
        />
      )}
    </Modal>
  );
}

export function UploadProgressPanel({ progress }: { progress: UploadState }) {
  const indexing = progress.phase === "indexing";

  return (
    <div className="upload-progress">
      <span className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        {indexing ? "正在解析、切分与向量化" : "正在上传文件"}
      </span>
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
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indexing ? 100 : progress.percent}
        aria-valuetext={indexing ? "上传完成，正在建立向量索引" : `${progress.percent}%`}
      >
        <span style={{ width: `${Math.max(progress.percent, 4)}%` }} />
      </div>
      <div className="upload-stages">
        <span className={indexing ? "complete" : "active"}>
          {indexing ? (
            <Check size={13} />
          ) : (
            <LoaderCircle className="spin" size={13} />
          )}
          上传文件{indexing ? "完成" : ` ${progress.percent}%`}
        </span>
        <span className={indexing ? "active" : "pending"}>
          {indexing ? (
            <LoaderCircle className="spin" size={13} />
          ) : (
            <Clock3 size={13} />
          )}
          解析、切分与向量化
        </span>
      </div>
    </div>
  );
}
