import {
  type RefObject,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { FileText, X } from "lucide-react";
import type { SourceReference } from "../types";
import { useMediaQuery } from "../features/ui/useMediaQuery";
import { Modal, ModalTitle } from "./Modal";
import { SourceItem } from "./SourceItem";

const COMPACT_SOURCES_QUERY = "(max-width: 860px)";

function focusReturnTarget(
  returnTarget: HTMLElement | null,
  fallbackTarget: HTMLElement | null,
): void {
  const target =
    returnTarget?.isConnected &&
    returnTarget.tabIndex >= 0 &&
    !returnTarget.matches(":disabled, [aria-disabled='true'], [inert], [inert] *")
      ? returnTarget
      : fallbackTarget;
  target?.focus({ preventScroll: true });
}

function SourcesContent({
  sources,
  highlightedRank,
  modal,
  closeButtonRef,
  onClose,
}: {
  sources: SourceReference[];
  highlightedRank: number | null;
  modal: boolean;
  closeButtonRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
}) {
  return (
    <>
      <header>
        <div>
          {modal ? <ModalTitle>引用来源</ModalTitle> : <h2>引用来源</h2>}
          <span>{sources.length ? `${sources.length} 个检索片段` : "等待检索结果"}</span>
        </div>
        <button
          ref={closeButtonRef}
          className="icon-button bordered sources-close"
          type="button"
          title="关闭引用来源"
          aria-label="关闭引用来源"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </header>
      <div className="sources-list">
        {sources.map((source) => (
          <SourceItem
            key={`${source.rank}-${source.chunk_id || source.source}`}
            source={source}
            highlighted={highlightedRank === source.rank}
          />
        ))}
        {sources.length === 0 && (
          <div className="sources-empty">
            <FileText size={26} />
            <strong>暂无引用来源</strong>
            <span>当前对话还没有检索结果</span>
          </div>
        )}
      </div>
    </>
  );
}

export function SourcesPanel({
  open,
  sources,
  highlightedRank = null,
  highlightRequestId = 0,
  fallbackFocusRef,
  onOpenChange,
}: {
  open: boolean;
  sources: SourceReference[];
  highlightedRank?: number | null;
  highlightRequestId?: number;
  fallbackFocusRef: RefObject<HTMLButtonElement | null>;
  onOpenChange: (open: boolean) => void;
}) {
  const compact = useMediaQuery(COMPACT_SOURCES_QUERY);
  const previousCompactRef = useRef(compact);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const [visibleHighlightRank, setVisibleHighlightRank] = useState<number | null>(null);
  const enteringCompact = compact && !previousCompactRef.current;

  useLayoutEffect(() => {
    if (!open) return;
    returnFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }, [open]);

  useLayoutEffect(() => {
    if (compact === previousCompactRef.current) return;
    previousCompactRef.current = compact;
    if (compact && open) {
      onOpenChange(false);
      queueMicrotask(() =>
        focusReturnTarget(returnFocusRef.current, fallbackFocusRef.current),
      );
    }
  }, [compact, fallbackFocusRef, onOpenChange, open]);

  useLayoutEffect(() => {
    if (!open || highlightedRank == null) {
      setVisibleHighlightRank(null);
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>(
        '.source-item[data-source-rank="' + highlightedRank + '"]',
      );
      setVisibleHighlightRank(highlightedRank);
      target?.scrollIntoView({ block: "nearest" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [highlightRequestId, highlightedRank, open, sources]);

  if (!open || enteringCompact) return null;

  if (!compact) {
    return (
      <aside className="sources-panel" aria-label="引用来源">
        <SourcesContent
          sources={sources}
          highlightedRank={visibleHighlightRank}
          modal={false}
          closeButtonRef={closeButtonRef}
          onClose={() => {
            onOpenChange(false);
            queueMicrotask(() =>
              focusReturnTarget(returnFocusRef.current, fallbackFocusRef.current),
            );
          }}
        />
      </aside>
    );
  }

  return (
    <Modal
      variant="sheet"
      initialFocusRef={closeButtonRef}
      fallbackFocusRef={fallbackFocusRef}
      onDismiss={() => onOpenChange(false)}
    >
      <SourcesContent
        sources={sources}
        highlightedRank={visibleHighlightRank}
        modal
        closeButtonRef={closeButtonRef}
        onClose={() => onOpenChange(false)}
      />
    </Modal>
  );
}
