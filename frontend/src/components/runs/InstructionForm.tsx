"use client";

import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { RunActionApi } from "@/hooks/useRunAction";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/Field";
import { Panel } from "@/components/ui/Panel";

const SUGGESTIONS = [
  "If shipment is delayed, escalate immediately.",
  "Do not contact the customer without human review.",
  "For this order, prioritize speed over cost.",
];

interface InstructionFormProps {
  runId: string;
  disabled: boolean;
  actions: RunActionApi;
}

export function InstructionForm({ runId, disabled, actions }: InstructionFormProps) {
  const [text, setText] = useState("");
  const [wakeAgent, setWakeAgent] = useState(true);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const ok = await actions.perform("instruction", () => api.addInstruction(runId, text.trim(), wakeAgent));
    if (ok) setText("");
  };

  return (
    <Panel title="Add instruction to this run" eyebrow="human in the loop">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <TextArea
          aria-label="Instruction"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. If shipment is delayed, escalate immediately."
          disabled={disabled}
          maxLength={1000}
        />
        <div className="flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={disabled}
              onClick={() => setText(suggestion)}
              className="rounded-full border border-dashed border-rule-strong px-2.5 py-0.5 text-xs text-ink-2 transition-colors hover:border-instruction hover:bg-instruction-wash hover:text-instruction disabled:opacity-45"
            >
              {suggestion}
            </button>
          ))}
        </div>
        <div className="flex items-center justify-between gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-2">
            <input type="checkbox" className="accent-[var(--signal)]" checked={wakeAgent} onChange={(e) => setWakeAgent(e.target.checked)} disabled={disabled} />
            Wake agent to apply it now
          </label>
          <Button type="submit" variant="primary" size="sm" disabled={disabled || !text.trim()} busy={actions.pending === "instruction"}>
            Add instruction
          </Button>
        </div>
      </form>
    </Panel>
  );
}
