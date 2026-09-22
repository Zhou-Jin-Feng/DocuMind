import { type RefObject, useEffect, useRef } from "react";
import { LoaderCircle, Trash2 } from "lucide-react";
import { Modal, ModalDescription, ModalTitle } from "./Modal";

export function ConfirmationDialog({
  title,
  description,
  confirmLabel,
  pendingLabel = "正在处理",
  pending = false,
  fallbackFocusRef,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: string;
  confirmLabel: string;
  pendingLabel?: string;
  pending?: boolean;
  fallbackFocusRef: RefObject<HTMLElement | null>;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const pendingStatusRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (pending) pendingStatusRef.current?.focus({ preventScroll: true });
  }, [pending]);

  return (
    <Modal
      variant="confirmation"
      initialFocusRef={cancelButtonRef}
      fallbackFocusRef={fallbackFocusRef}
      dismissible={!pending}
      onDismiss={onCancel}
    >
      <div className="confirmation-icon" aria-hidden="true">
        <Trash2 size={20} />
      </div>
      <div
        ref={pendingStatusRef}
        className="confirmation-copy"
        role={pending ? "status" : undefined}
        aria-label={pending ? pendingLabel : undefined}
        aria-busy={pending || undefined}
        tabIndex={pending ? 0 : -1}
      >
        <ModalTitle>{title}</ModalTitle>
        <ModalDescription>{description}</ModalDescription>
      </div>
      <div className="confirmation-actions">
        <button
          ref={cancelButtonRef}
          className="secondary-button"
          type="button"
          onClick={onCancel}
          disabled={pending}
        >
          取消
        </button>
        <button
          className="danger-button"
          type="button"
          onClick={onConfirm}
          disabled={pending}
        >
          {pending && <LoaderCircle className="spin" size={16} />}
          {pending ? pendingLabel : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
