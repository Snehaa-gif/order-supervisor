import type { TimelineKind } from "@/lib/api";

export interface KindStyle {
  label: string;
  glyph: string;
  /** Classes for the small kind chip. */
  chip: string;
  /** Colour of the dot on the timeline rail. */
  dot: string;
}

export const KIND_STYLES: Record<TimelineKind, KindStyle> = {
  event: { label: "Event", glyph: "◆", chip: "bg-transit-wash text-transit", dot: "bg-transit" },
  classification: { label: "Policy", glyph: "⑂", chip: "bg-paused-wash text-paused", dot: "bg-paused" },
  wake: { label: "Wake", glyph: "☀", chip: "bg-awake-wash text-awake", dot: "bg-awake" },
  agent: { label: "Agent", glyph: "✦", chip: "bg-sleeping-wash text-sleeping", dot: "bg-sleeping" },
  tool: { label: "Tool", glyph: "⚙", chip: "bg-signal-wash text-signal-ink", dot: "bg-signal" },
  sleep: { label: "Sleep", glyph: "☾", chip: "bg-sleeping-wash text-sleeping", dot: "bg-sleeping/60" },
  instruction: { label: "Instruction", glyph: "✎", chip: "bg-instruction-wash text-instruction", dot: "bg-instruction" },
  control: { label: "Control", glyph: "■", chip: "bg-stopped-wash text-stopped", dot: "bg-stopped" },
  memory: { label: "Memory", glyph: "◎", chip: "bg-done-wash text-done", dot: "bg-done" },
  system: { label: "System", glyph: "○", chip: "bg-sunken text-ink-2", dot: "bg-ink-3" },
};
