import Link from "next/link";
import type { Run } from "@/lib/api";
import { formatDateTime, humanize } from "@/lib/format";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { WakeState } from "@/components/runs/WakeState";

interface RunHeaderProps {
  run: Run;
}

export function RunHeader({ run }: RunHeaderProps) {
  return (
    <header className="flex flex-col gap-4">
      <Link href="/" className="w-fit font-mono text-xs text-ink-3 hover:text-signal">
        ← All runs
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">
            Order · supervised by {run.supervisor_name}
          </p>
          <h1 className="font-mono text-4xl font-medium tracking-tight">{run.order_id}</h1>
          <p className="mt-1 font-mono text-[11px] text-ink-3">
            workflow {run.workflow_id} · run {run.id} · started {formatDateTime(run.created_at)}
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end">
          <StatusBadge status={run.status} size="lg" />
          <WakeState status={run.status} nextWakeAt={run.next_wake_at} variant="hero" />
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-[var(--radius-panel)] border border-rule bg-rule md:grid-cols-4">
        <Metric label="Order status" value={humanize(run.order_status)} />
        <Metric label="Agent turns" value={String(run.turn_count)} mono />
        <Metric label="Unseen events" value={String(run.pending_events)} mono />
        <Metric label="Instructions" value={String(run.instructions.length)} mono />
      </dl>
    </header>
  );
}

function Metric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-surface px-4 py-3">
      <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">{label}</dt>
      <dd className={`mt-0.5 text-xl font-medium text-ink ${mono ? "font-mono tabular-nums" : ""}`}>{value}</dd>
    </div>
  );
}
