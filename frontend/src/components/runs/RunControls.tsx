"use client";

import { useEffect, useState } from "react";
import { api, isTerminal, type Run } from "@/lib/api";
import type { RunActionApi } from "@/hooks/useRunAction";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import { Panel } from "@/components/ui/Panel";

const CONFIRM_WINDOW_MS = 5000;

interface RunControlsProps {
  run: Run;
  actions: RunActionApi;
}

export function RunControls({ run, actions }: RunControlsProps) {
  const [note, setNote] = useState("");
  const [confirmingTerminate, setConfirmingTerminate] = useState(false);
  const closed = isTerminal(run.status) || run.status === "completing";
  const paused = run.status === "paused";
  const { pending, perform } = actions;

  // The terminate confirmation disarms itself if not clicked again within a few seconds.
  useEffect(() => {
    if (!confirmingTerminate) return;
    const timer = setTimeout(() => setConfirmingTerminate(false), CONFIRM_WINDOW_MS);
    return () => clearTimeout(timer);
  }, [confirmingTerminate]);

  const interrupt = async () => {
    const ok = await perform("interrupt", () => api.interrupt(run.id, note.trim()));
    if (ok) setNote("");
  };

  const terminate = async () => {
    if (!confirmingTerminate) {
      setConfirmingTerminate(true);
      return;
    }
    setConfirmingTerminate(false);
    await perform("terminate", () => api.terminate(run.id, "Terminated by operator from the UI"));
  };

  return (
    <Panel title="Run controls" eyebrow="operator">
      <div className="flex flex-col gap-3">
        <div className="flex gap-2">
          <TextInput
            aria-label="Note for the agent (optional)"
            placeholder="Optional note: why wake the agent?"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={closed}
            maxLength={500}
          />
          <Button variant="primary" onClick={interrupt} disabled={closed} busy={pending === "interrupt"} title="Wake the agent now for an immediate review">
            Interrupt · wake now
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          {paused ? (
            <Button onClick={() => perform("resume", () => api.resume(run.id))} disabled={closed} busy={pending === "resume"}>
              ▶ Resume
            </Button>
          ) : (
            <Button onClick={() => perform("pause", () => api.pause(run.id))} disabled={closed} busy={pending === "pause"}>
              ❚❚ Pause
            </Button>
          )}
          <Button variant="danger" onClick={terminate} disabled={closed} busy={pending === "terminate"} aria-live="polite">
            {confirmingTerminate ? "Click again to terminate" : "■ Terminate"}
          </Button>
        </div>
        <p className="text-xs leading-relaxed text-ink-3">
          {closed
            ? "This run is closed; controls are disabled."
            : paused
              ? "Paused: events are still recorded, but the agent won't act until you resume."
              : "Terminate asks the agent to write its final report, then closes the workflow."}
        </p>
      </div>
    </Panel>
  );
}
