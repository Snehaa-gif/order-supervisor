import type { JsonObject, JsonValue, TimelineEntry } from "@/lib/api";
import { formatClock } from "@/lib/format";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { KIND_STYLES } from "@/components/runs/timelineKinds";

interface TimelineItemProps {
  entry: TimelineEntry;
}

const str = (value: JsonValue | undefined): string => (typeof value === "string" ? value : "");

export function TimelineItem({ entry }: TimelineItemProps) {
  const style = KIND_STYLES[entry.kind] ?? KIND_STYLES.system;
  const hasDetail = Object.keys(entry.detail).length > 0;
  const summary = summarize(entry);

  return (
    <li className="relative grid grid-cols-[64px_16px_minmax(0,1fr)] gap-x-3 pb-4 last:pb-0">
      <time dateTime={entry.at} className="pt-0.5 text-right font-mono text-[11px] tabular-nums text-ink-3">
        {formatClock(entry.at)}
      </time>
      <span className="relative flex justify-center" aria-hidden>
        <span className="absolute bottom-[-16px] top-0 w-px bg-rule" />
        <span className={`relative mt-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-surface ${style.dot}`} />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded-[4px] px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.08em] ${style.chip}`}>
            <span aria-hidden>{style.glyph}</span>
            {style.label}
          </span>
          {entry.important && <span className="h-1.5 w-1.5 rounded-full bg-signal" title="Important" aria-label="Important" />}
        </div>
        {entry.kind === "agent" ? (
          <p className="mt-1 rounded-[var(--radius-control)] bg-sleeping-wash/60 px-3 py-2 text-sm italic leading-relaxed text-ink">
            “{entry.title}”
          </p>
        ) : (
          <p className={`mt-1 text-sm leading-snug ${entry.important ? "font-medium text-ink" : "text-ink-2"}`}>
            {entry.kind === "tool" || entry.kind === "event" ? <span className="font-mono">{entry.title}</span> : entry.title}
          </p>
        )}
        {summary && <p className="mt-0.5 text-xs leading-relaxed text-ink-3">{summary}</p>}
        {hasDetail && (
          <details className="group mt-1">
            <summary className="w-fit cursor-pointer list-none font-mono text-[11px] text-ink-3 hover:text-signal">
              <span className="group-open:hidden">+ details</span>
              <span className="hidden group-open:inline">− hide details</span>
            </summary>
            <div className="mt-1.5">
              <JsonBlock value={entry.detail} />
            </div>
          </details>
        )}
      </div>
    </li>
  );
}

/** A one-line, human-readable digest of the entry's detail. */
function summarize(entry: TimelineEntry): string {
  const detail: JsonObject = entry.detail;
  switch (entry.kind) {
    case "classification":
    case "wake":
      return str(detail.reason) || str(detail.note);
    case "sleep":
      return str(detail.reason);
    case "control":
      return str(detail.note);
    case "memory":
      return str(detail.summary) || str(detail.note);
    case "event": {
      const payload = detail.payload;
      return payload && typeof payload === "object" && Object.keys(payload).length ? JSON.stringify(payload) : "";
    }
    case "tool": {
      const ok = detail.ok === true;
      const output = detail.output as JsonObject | undefined;
      if (!ok) return `Failed: ${str(output?.error)}`;
      const args = detail.args as JsonObject | undefined;
      return str(args?.message) || str(args?.reason) || str(args?.note) || "";
    }
    case "system":
      return str(detail.error);
    default:
      return "";
  }
}
