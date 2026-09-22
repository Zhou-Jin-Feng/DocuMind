import { type ReactNode } from "react";
import { Check, CircleAlert, Info, TriangleAlert, X } from "lucide-react";

export type NoticeKind = "success" | "error" | "warning" | "info";
export type NoticePlacement = "sidebar" | "banner" | "inline";

const DEFAULT_ICONS = {
  success: <Check size={16} />,
  error: <CircleAlert size={16} />,
  warning: <TriangleAlert size={16} />,
  info: <Info size={16} />,
};

export function Notice({
  kind,
  placement,
  title,
  icon,
  action,
  onDismiss,
  announce,
  children,
}: {
  kind: NoticeKind;
  placement: NoticePlacement;
  title?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
  announce?: "assertive" | "polite" | "off";
  children: ReactNode;
}) {
  const announcement = announce ?? (kind === "error" ? "assertive" : "polite");
  return (
    <div
      className={`notice notice-${placement} notice-${kind}`}
      role={
        announcement === "off"
          ? undefined
          : announcement === "assertive"
            ? "alert"
            : "status"
      }
      aria-live={announcement === "off" ? undefined : announcement}
      aria-atomic={announcement === "off" ? undefined : "true"}
    >
      <span className="notice-icon" aria-hidden="true">
        {icon ?? DEFAULT_ICONS[kind]}
      </span>
      <div className="notice-copy">
        {title && <strong>{title}</strong>}
        <span>{children}</span>
      </div>
      {action && <div className="notice-action">{action}</div>}
      {onDismiss && (
        <button
          className="notice-close"
          type="button"
          title="关闭提示"
          aria-label="关闭提示"
          onClick={onDismiss}
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
