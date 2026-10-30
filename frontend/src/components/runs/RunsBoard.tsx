"use client";

import Link from "next/link";
import { usePolling } from "@/hooks/usePolling";
import { api, isTerminal } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";
import { EmptyState, Notice } from "@/components/ui/Notice";
import { RunsTable } from "@/components/runs/RunsTable";

const RUNS_POLL_MS = 3000;

export function RunsBoard() {
  const { data: runs, error, isLoading } = usePolling(() => api.listRuns(), RUNS_POLL_MS);
  const active = runs?.filter((run) => !isTerminal(run.status)) ?? [];
  const closed = runs?.filter((run) => isTerminal(run.status)) ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">Supervision runs</p>
          <h1 className="text-3xl font-semibold tracking-tight">One AI supervisor per order.</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-2">
            Each run is a long-lived Temporal workflow. The agent sleeps between turns and wakes on start, on important
            events, or at the time it scheduled for itself.
          </p>
        </div>
        <dl className="flex gap-6 font-mono text-sm">
          <Stat label="Active" value={runs ? active.length : "—"} />
          <Stat label="Closed" value={runs ? closed.length : "—"} />
        </dl>
      </div>

      {error && !runs && <Notice tone="error">{error.message}</Notice>}

      <Panel title="Active runs" eyebrow="01 · live">
        {isLoading ? (
          <p className="text-sm text-ink-3">Loading runs…</p>
        ) : active.length === 0 ? (
          <EmptyState title="No active runs">
            <Link href="/runs/new" className="font-medium text-signal underline underline-offset-4 hover:text-signal-ink">
              Start a supervisor for an order
            </Link>
          </EmptyState>
        ) : (
          <RunsTable runs={active} variant="active" />
        )}
      </Panel>

      <Panel title="Completed runs" eyebrow="02 · history">
        {isLoading ? (
          <p className="text-sm text-ink-3">Loading runs…</p>
        ) : closed.length === 0 ? (
          <EmptyState title="No completed runs yet" />
        ) : (
          <RunsTable runs={closed} variant="closed" />
        )}
      </Panel>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="text-right">
      <dt className="text-[11px] uppercase tracking-[0.14em] text-ink-3">{label}</dt>
      <dd className="text-3xl font-medium tabular-nums text-ink">{value}</dd>
    </div>
  );
}
