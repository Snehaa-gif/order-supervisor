import type { ReactNode } from "react";

interface NoticeProps {
  tone?: "error" | "info" | "success";
  title?: string;
  children: ReactNode;
}

const TONES = {
  error: "border-stopped/30 bg-stopped-wash text-stopped",
  info: "border-sleeping/25 bg-sleeping-wash text-sleeping",
  success: "border-done/30 bg-done-wash text-done",
};

/** Inline message block for errors, hints and confirmations. */
export function Notice({ tone = "info", title, children }: NoticeProps) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-[var(--radius-control)] border px-3 py-2 text-sm ${TONES[tone]}`}>
      {title && <p className="font-semibold">{title}</p>}
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}

interface ErrorListProps {
  messages: string[];
}

export function ErrorList({ messages }: ErrorListProps) {
  if (messages.length === 0) return null;
  if (messages.length === 1) return <Notice tone="error">{messages[0]}</Notice>;
  return (
    <Notice tone="error" title="Please fix the following">
      <ul className="mt-1 list-disc pl-5">
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    </Notice>
  );
}

interface EmptyStateProps {
  title: string;
  children?: ReactNode;
}

export function EmptyState({ title, children }: EmptyStateProps) {
  return (
    <div className="rounded-[var(--radius-control)] border border-dashed border-rule-strong px-4 py-8 text-center">
      <p className="text-sm font-medium text-ink-2">{title}</p>
      {children && <div className="mt-2 text-sm text-ink-3">{children}</div>}
    </div>
  );
}
