import type { Run } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";

interface MemoryPanelProps {
  run: Run;
}

export function MemoryPanel({ run }: MemoryPanelProps) {
  const guidance = run.wake_guidance ?? {};
  const wakeOn = guidance.wake_on ?? [];
  const ignore = guidance.ignore ?? [];

  return (
    <Panel title="Agent memory" eyebrow="compact context">
      <div className="flex flex-col gap-4">
        <div>
          <p className="mb-1 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">Memory summary</p>
          {run.memory_summary ? (
            <p className="whitespace-pre-wrap border-l-2 border-sleeping pl-3 text-sm leading-relaxed text-ink">{run.memory_summary}</p>
          ) : (
            <p className="text-sm text-ink-3">The agent hasn&apos;t written its memory yet.</p>
          )}
        </div>

        <div>
          <p className="mb-1 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">Wake guidance (set by the agent)</p>
          {wakeOn.length === 0 && ignore.length === 0 && !guidance.note ? (
            <p className="text-sm text-ink-3">Default policy.</p>
          ) : (
            <div className="flex flex-col gap-1.5 text-sm">
              <TagRow label="Wake on" tags={wakeOn} tone="bg-awake-wash text-awake" />
              <TagRow label="Ignore" tags={ignore} tone="bg-paused-wash text-paused" />
              {guidance.note && <p className="text-xs italic text-ink-2">“{guidance.note}”</p>}
            </div>
          )}
        </div>

        <div>
          <p className="mb-1 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">Run instructions</p>
          {run.instructions.length === 0 ? (
            <p className="text-sm text-ink-3">None. Add one below to steer this run.</p>
          ) : (
            <ol className="flex flex-col gap-1.5">
              {run.instructions.map((instruction, index) => (
                <li key={`${index}-${instruction}`} className="flex gap-2 rounded-[var(--radius-control)] bg-instruction-wash px-3 py-1.5 text-sm text-ink">
                  <span className="font-mono text-xs text-instruction">{String(index + 1).padStart(2, "0")}</span>
                  {instruction}
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </Panel>
  );
}

function TagRow({ label, tags, tone }: { label: string; tags: string[]; tone: string }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="w-16 text-xs text-ink-3">{label}</span>
      {tags.length === 0 ? (
        <span className="text-xs text-ink-3">—</span>
      ) : (
        tags.map((tag) => (
          <span key={tag} className={`rounded-[4px] px-1.5 py-0.5 font-mono text-[11px] ${tone}`}>
            {tag}
          </span>
        ))
      )}
    </div>
  );
}
