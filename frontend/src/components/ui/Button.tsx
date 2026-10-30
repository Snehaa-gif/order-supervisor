import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  busy?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-ink text-paper border-ink hover:bg-signal hover:border-signal active:bg-signal-ink disabled:hover:bg-ink disabled:hover:border-ink",
  secondary:
    "bg-surface text-ink border-rule-strong hover:border-ink hover:bg-sunken active:bg-rule disabled:hover:bg-surface disabled:hover:border-rule-strong",
  ghost: "bg-transparent text-ink-2 border-transparent hover:text-ink hover:bg-sunken active:bg-rule",
  danger:
    "bg-surface text-stopped border-stopped/40 hover:bg-stopped hover:text-white hover:border-stopped active:bg-stopped/90 disabled:hover:bg-surface disabled:hover:text-stopped",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-10 px-4 text-sm",
};

export function Button({ variant = "secondary", size = "md", busy = false, className = "", children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] border font-medium transition-[background-color,color,border-color,transform] duration-150 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-45 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {busy && <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}
      {children}
    </button>
  );
}
