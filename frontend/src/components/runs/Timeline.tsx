"use client";

import { useMemo, useState } from "react";
import { TIMELINE_KINDS, type TimelineEntry, type TimelineKind } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/Notice";
import { TimelineItem } from "@/components/runs/TimelineItem";
import { KIND_STYLES } from "@/components/runs/timelineKinds";

interface TimelineProps {
  entries: TimelineEntry[];
}

export function Timeline({ entries }: TimelineProps) {
  const [newestFirst, setNewestFirst] = useState(true);
  const [importantOnly, setImportantOnly] = useState(false);
  const [hidden, setHidden] = useState<ReadonlySet<TimelineKind>>(new Set());

  const counts = useMemo(() => {
    const result = new Map<TimelineKind, number>();
    for (const entry of entries) result.set(entry.kind, (result.get(entry.kind) ?? 0) + 1);
    return result;
  }, [entries]);

  const visible = useMemo(() => {
    const filtered = entries.filter((e) => !hidden.has(e.kind) && (!importantOnly || e.important));
    return newestFirst ? [...filtered].reverse() : filtered;
  }, [entries, hidden, importantOnly, newestFirst]);

  const toggleKind = (kind: TimelineKind) =>
    setHidden((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  const controls = (
    <>
      <button
        type="button"
        onClick={() => setImportantOnly((v) => !v)}
        aria-pressed={importantOnly}
        className={`rounded-[var(--radius-control)] border px-2 py-1 font-mono text-[11px] transition-colors ${
          importantOnly ? "border-ink bg-ink text-paper" : "border-rule-strong text-ink-2 hover:border-ink"
        }`}
      >
        ● important only
      </button>
      <button
        type="button"
        onClick={() => setNewestFirst((v) => !v)}
        className="rounded-[var(--radius-control)] border border-rule-strong px-2 py-1 font-mono text-[11px] text-ink-2 transition-colors hover:border-ink"
      >
        {newestFirst ? "↓ newest first" : "↑ oldest first"}
      </button>
    </>
  );

  return (
    <Panel title="Timeline" eyebrow={`${entries.length} entries`} actions={controls}>
      <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Filter by kind">
        {TIMELINE_KINDS.map((kind) => {
          const style = KIND_STYLES[kind];
          const shown = !hidden.has(kind);
          return (
            <button
              key={kind}
              type="button"
              aria-pressed={shown}
              onClick={() => toggleKind(kind)}
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-[11px] transition-colors ${
                shown ? `border-transparent ${style.chip}` : "border-rule-strong bg-surface text-ink-3 line-through hover:text-ink-2"
              }`}
            >
              <span aria-hidden>{style.glyph}</span>
              {style.label}
              <span className="opacity-60">{counts.get(kind) ?? 0}</span>
            </button>
          );
        })}
      </div>
      {visible.length === 0 ? (
        <EmptyState title={entries.length === 0 ? "Nothing has happened yet" : "No entries match these filters"} />
      ) : (
        <ol className="flex flex-col">
          {visible.map((entry) => (
            <TimelineItem key={entry.id} entry={entry} />
          ))}
        </ol>
      )}
    </Panel>
  );
}
