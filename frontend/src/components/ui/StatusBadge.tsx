import type { RunStatus } from "@/lib/api";

interface StatusStyle {
  label: string;
  className: string;
  dot: string;
  live?: boolean;
}

export const STATUS_STYLES: Record<RunStatus, StatusStyle> = {
  starting: { label: "Starting", className: "bg-transit-wash text-transit", dot: "bg-transit", live: true },
  awake: { label: "Awake", className: "bg-awake-wash text-awake", dot: "bg-awake", live: true },
  sleeping: { label: "Sleeping", className: "bg-sleeping-wash text-sleeping", dot: "bg-sleeping" },
  paused: { label: "Paused", className: "bg-paused-wash text-paused", dot: "bg-paused" },
  completing: { label: "Wrapping up", className: "bg-transit-wash text-transit", dot: "bg-transit", live: true },
  completed: { label: "Completed", className: "bg-done-wash text-done", dot: "bg-done" },
  terminated: { label: "Terminated", className: "bg-stopped-wash text-stopped", dot: "bg-stopped" },
  failed: { label: "Failed", className: "bg-stopped-wash text-stopped", dot: "bg-stopped" },
};

interface StatusBadgeProps {
  status: RunStatus;
  size?: "sm" | "lg";
}

export function StatusBadge({ status, size = "sm" }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.failed;
  const sizing = size === "lg" ? "px-3 py-1.5 text-sm gap-2" : "px-2 py-0.5 text-xs gap-1.5";
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${sizing} ${style.className}`}>
      <span className={`h-2 w-2 rounded-full ${style.dot} ${style.live ? "animate-pulse-dot" : ""}`} aria-hidden />
      {style.label}
    </span>
  );
}
