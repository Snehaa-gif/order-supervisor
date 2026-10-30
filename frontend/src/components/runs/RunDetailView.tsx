"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { useRunAction } from "@/hooks/useRunAction";
import { ApiError, api, isTerminal } from "@/lib/api";
import { EVENT_PRESETS } from "@/lib/events";
import { Notice } from "@/components/ui/Notice";
import { ActionsPanel } from "@/components/runs/ActionsPanel";
import { EventInjector } from "@/components/runs/EventInjector";
import { FinalReportPanel } from "@/components/runs/FinalReportPanel";
import { InstructionForm } from "@/components/runs/InstructionForm";
import { MemoryPanel } from "@/components/runs/MemoryPanel";
import { RunControls } from "@/components/runs/RunControls";
import { RunHeader } from "@/components/runs/RunHeader";
import { Timeline } from "@/components/runs/Timeline";

const RUN_POLL_MS = 2000;

export function RunDetailView() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [eventTypes, setEventTypes] = useState<string[]>(Object.keys(EVENT_PRESETS));
  const [closedRunId, setClosedRunId] = useState<string | null>(null);

  const load = useCallback(() => api.getRun(runId), [runId]);
  const { data: run, error, isLoading, refresh } = usePolling(load, RUN_POLL_MS, closedRunId !== runId);
  const actions = useRunAction(refresh);

  // Stop polling once the run is closed and its report has been written.
  useEffect(() => {
    if (!run || !isTerminal(run.status)) return;
    const timer = setTimeout(() => setClosedRunId(run.id), 0);
    return () => clearTimeout(timer);
  }, [run]);

  useEffect(() => {
    let cancelled = false;
    api
      .meta()
      .then((meta) => {
        if (!cancelled) setEventTypes(meta.event_types);
      })
      .catch(() => {
        // Keep the built-in preset list if metadata can't be loaded.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading && !run) return <p className="text-sm text-ink-3">Loading run…</p>;
  if (!run) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="flex flex-col gap-3">
        <Notice tone="error" title={notFound ? "Run not found" : "Could not load this run"}>
          {notFound ? `No run with id ${runId}.` : error?.message}
        </Notice>
        <Link href="/" className="text-sm text-signal underline underline-offset-4">
          Back to all runs
        </Link>
      </div>
    );
  }

  const inactive = isTerminal(run.status) || run.status === "completing";

  return (
    <div className="flex flex-col gap-6">
      <RunHeader run={run} />
      {error && <Notice tone="error">Live updates paused: {error.message}</Notice>}
      {run.final_report && <FinalReportPanel report={run.final_report} closeReason={run.close_reason} />}
      {run.status === "failed" && !run.final_report && (
        <Notice tone="error" title="Run failed to start">
          {run.close_reason}
        </Notice>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="flex min-w-0 flex-col gap-6">
          <div className="grid gap-6 xl:grid-cols-2">
            <MemoryPanel run={run} />
            <ActionsPanel executions={run.tool_executions} />
          </div>
          <Timeline entries={run.timeline} />
        </div>
        <aside className="flex flex-col gap-6" aria-label="Operator tools">
          <RunControls run={run} actions={actions} />
          <EventInjector runId={run.id} eventTypes={eventTypes} disabled={inactive} onSent={refresh} />
          <InstructionForm runId={run.id} disabled={inactive} actions={actions} />
        </aside>
      </div>
    </div>
  );
}
