import {
  type ComponentPropsWithoutRef,
  type ReactNode,
  type RefObject,
  useLayoutEffect,
  useRef,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";

type ModalVariant = "document" | "confirmation" | "sheet";

const VARIANT_CLASS: Record<ModalVariant, string> = {
  document: "document-dialog",
  confirmation: "conversation-confirm-dialog",
  sheet: "sources-panel sources-dialog",
};

function canReceiveFocus(element: HTMLElement | null): element is HTMLElement {
  if (!element?.isConnected) return false;
  if (element.matches(":disabled, [aria-disabled='true'], [inert], [inert] *")) {
    return false;
  }
  return true;
}

function focusWithoutScrolling(element: HTMLElement | null): void {
  if (!canReceiveFocus(element)) return;
  element.focus({ preventScroll: true });
}

export function Modal({
  variant,
  initialFocusRef,
  fallbackFocusRef,
  restoreFocus = "trigger",
  dismissible = true,
  onDismiss,
  children,
}: {
  variant: ModalVariant;
  initialFocusRef: RefObject<HTMLElement | null>;
  fallbackFocusRef: RefObject<HTMLElement | null>;
  restoreFocus?: "trigger" | "fallback";
  dismissible?: boolean;
  onDismiss: () => void;
  children: ReactNode;
}) {
  const returnFocusRef = useRef<HTMLElement | null>(
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  );
  const restoreFocusRef = useRef(restoreFocus);
  restoreFocusRef.current = restoreFocus;
  const lifecycleGenerationRef = useRef(0);

  useLayoutEffect(() => {
    const generation = ++lifecycleGenerationRef.current;
    return () => {
      queueMicrotask(() => {
        if (lifecycleGenerationRef.current !== generation) return;
        window.requestAnimationFrame(() => {
          if (lifecycleGenerationRef.current !== generation) return;
          const returnTarget =
            restoreFocusRef.current === "trigger" &&
            canReceiveFocus(returnFocusRef.current)
              ? returnFocusRef.current
              : fallbackFocusRef.current;
          focusWithoutScrolling(returnTarget);
        });
      });
    };
  }, [fallbackFocusRef]);

  return (
    <Dialog.Root
      open
      modal
      onOpenChange={(open) => {
        if (!open && dismissible) onDismiss();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className={`modal-overlay modal-overlay-${variant}`} />
        <Dialog.Content
          className={`modal-content modal-content-${variant} ${VARIANT_CLASS[variant]}`}
          aria-modal="true"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            focusWithoutScrolling(initialFocusRef.current);
          }}
          onCloseAutoFocus={(event) => event.preventDefault()}
          onEscapeKeyDown={(event) => {
            if (!dismissible) event.preventDefault();
          }}
          onPointerDownOutside={(event) => {
            if (!dismissible) event.preventDefault();
          }}
          onInteractOutside={(event) => {
            if (!dismissible) event.preventDefault();
          }}
        >
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function ModalTitle(
  props: ComponentPropsWithoutRef<typeof Dialog.Title>,
) {
  return <Dialog.Title {...props} />;
}

export function ModalDescription(
  props: ComponentPropsWithoutRef<typeof Dialog.Description>,
) {
  return <Dialog.Description {...props} />;
}
