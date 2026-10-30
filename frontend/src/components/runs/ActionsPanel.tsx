import type { JsonValue, ToolExecution } from "@/lib/api";
import { formatClock } from "@/lib/format";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/Notice";

const TOOL_LABELS: Record<string, { label: string; accent: string }> = {
  send_customer_message: { label: "Customer message", accent: "border-l-sleeping" },
  create_internal_note: { label: "Internal note", accent: "border-l-paused" },
  escalate_issue: { label: "Escalation", accent: "border-l-stopped" },
  mark_order_for_review: { label: "Flagged for review", accent: "border-l-awake" },
};

interface ActionsPanelProps {
  executions: ToolExecution[];
}

const text = (value: JsonValue | undefined): string => (value === undefined || value === null ? "" : String(value));

/** The simulated outbox: every side effect the agent's tools produced. */
export function ActionsPanel({ executions }: ActionsPanelProps) {
  return (
    <Panel title="Actions taken" eyebrow={`outbox · ${executions.length}`}>
      {executions.length === 0 ? (
        <EmptyState title="No actions yet">The agent hasn&apos;t needed to message, escalate or flag anything.</EmptyState>
      ) : (
        <ol className="flex flex-col gap-2">
          {[...executions].reverse().map((execution, index) => {
            const meta = TOOL_LABELS[execution.tool] ?? { label: execution.tool, accent: "border-l-ink-3" };
            const reference = Object.entries(execution.result).find(([key]) => key.endsWith("_id"))?.[1];
            return (
              <li key={`${execution.created_at}-${index}`} className={`rounded-[var(--radius-control)] border border-rule border-l-4 ${meta.accent} bg-surface px-3 py-2`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold">{meta.label}</span>
                  <span className="font-mono text-[11px] text-ink-3">
                    {text(reference)} · {formatClock(execution.created_at)}
                  </span>
                </div>
                <ActionBody execution={execution} />
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

function ActionBody({ execution }: { execution: ToolExecution }) {
  const { args } = execution;
  switch (execution.tool) {
    case "send_customer_message":
      return (
        <p className="mt-1 text-sm leading-relaxed text-ink-2">
          <span className="font-mono text-[11px] uppercase text-ink-3">{text(args.channel)} → customer: </span>
          {text(args.message)}
        </p>
      );
    case "escalate_issue":
      return (
        <p className="mt-1 text-sm text-ink-2">
          <span className="font-mono text-[11px] uppercase text-stopped">
            {text(args.severity)} · {text(args.team)}
          </span>{" "}
          {text(args.reason)}
        </p>
      );
    case "create_internal_note":
      return <p className="mt-1 text-sm text-ink-2">{text(args.note)}</p>;
    case "mark_order_for_review":
      return <p className="mt-1 text-sm text-ink-2">{text(args.reason)}</p>;
    default:
      return <p className="mt-1 font-mono text-xs text-ink-2">{JSON.stringify(args)}</p>;
  }
}
