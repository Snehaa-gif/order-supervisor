"use client";

import { useNow } from "@/hooks/useNow";
import type { RunStatus } from "@/lib/api";
import { formatCountdown } from "@/lib/format";

interface WakeStateProps {
  status: RunStatus;
  nextWakeAt: string | null;
  /** "compact" for table cells, "hero" for the run header. */
  variant?: "compact" | "hero";
}

/** One-line description of what the agent is doing right now, with a live countdown when asleep. */
export function WakeState({ status, nextWakeAt, variant = "compact" }: WakeStateProps) {
  const now = useNow();
  const text = describe(status, nextWakeAt, now);
  if (variant === "compact") return <span className="font-mono text-xs text-ink-2">{text}</span>;
  return <span className="font-mono text-sm text-ink-2">{text}</span>;
}

function describe(status: RunStatus, nextWakeAt: string | null, now: number): string {
  switch (status) {
    case "starting":
      return "Starting workflow…";
    case "awake":
      return "Awake — thinking…";
    case "completing":
      return "Writing final report…";
    case "paused":
      return "Paused — agent will not act";
    case "sleeping": {
      if (!nextWakeAt) return "Sleeping — waiting for events";
      const remaining = new Date(nextWakeAt).getTime() - now;
      return remaining > 0 ? `Sleeping — wakes in ${formatCountdown(remaining)}` : "Waking up…";
    }
    default:
      return "—";
  }
}
