import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}

/** A titled surface. The eyebrow is a small mono label that numbers/categorises the section. */
export function Panel({ title, eyebrow, actions, children, className = "", id }: PanelProps) {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={`rounded-[var(--radius-panel)] border border-rule bg-surface shadow-raised ${className}`}
    >
      <header className="flex items-start justify-between gap-3 border-b border-rule px-5 pb-3 pt-4">
        <div>
          {eyebrow && <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">{eyebrow}</p>}
          <h2 id={headingId} className="text-[15px] font-semibold tracking-tight text-ink">
            {title}
          </h2>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}
