"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, errorMessage, type JsonObject } from "@/lib/api";
import { CRITICAL_EVENTS, EVENT_PRESETS, SCENARIOS, SCENARIO_STEP_DELAY_MS, TERMINAL_EVENTS, type Scenario } from "@/lib/events";
import { humanize } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { TextArea, TextInput } from "@/components/ui/Field";
import { Panel } from "@/components/ui/Panel";
import { useToast } from "@/components/ui/Toaster";

interface EventInjectorProps {
  runId: string;
  eventTypes: string[];
  disabled: boolean;
  onSent: () => Promise<void>;
}

interface ScenarioProgress {
  id: string;
  step: number;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function toneFor(type: string): string {
  if (TERMINAL_EVENTS.has(type)) return "border-done/40 hover:border-done hover:bg-done-wash";
  if (CRITICAL_EVENTS.has(type)) return "border-awake/40 hover:border-awake hover:bg-awake-wash";
  return "border-rule-strong hover:border-ink hover:bg-sunken";
}

export function EventInjector({ runId, eventTypes, disabled, onSent }: EventInjectorProps) {
  const { notify } = useToast();
  const [sending, setSending] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioProgress | null>(null);
  const [customType, setCustomType] = useState("warehouse_fire_alarm");
  const [customPayload, setCustomPayload] = useState('{ "warehouse": "BLR-2" }');
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
    };
  }, []);

  const send = async (type: string, payload: JsonObject): Promise<boolean> => {
    setSending(type);
    try {
      await api.sendEvent(runId, type, payload);
      notify(`Sent ${type}`, "success");
      await onSent();
      return true;
    } catch (error: unknown) {
      notify(errorMessage(error), "error");
      return false;
    } finally {
      setSending(null);
    }
  };

  const playScenario = async (item: Scenario) => {
    for (const [index, step] of item.steps.entries()) {
      if (cancelled.current) return;
      setScenario({ id: item.id, step: index });
      const ok = await send(step.type, step.payload);
      if (!ok) break;
      if (index < item.steps.length - 1) await sleep(SCENARIO_STEP_DELAY_MS);
    }
    if (!cancelled.current) setScenario(null);
  };

  const sendCustom = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    let payload: unknown;
    try {
      payload = customPayload.trim() ? JSON.parse(customPayload) : {};
    } catch {
      notify("Payload is not valid JSON", "error");
      return;
    }
    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      notify("Payload must be a JSON object", "error");
      return;
    }
    await send(customType.trim(), payload as JsonObject);
  };

  const busy = sending !== null || scenario !== null;

  return (
    <Panel title="Event generator" eyebrow="simulate the outside world">
      <div className="flex flex-col gap-5">
        <div>
          <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">Scenarios</p>
          <div className="grid gap-2">
            {SCENARIOS.map((item) => {
              const running = scenario?.id === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => playScenario(item)}
                  disabled={disabled || busy}
                  className="group rounded-[var(--radius-control)] border border-rule-strong px-3 py-2 text-left transition-colors hover:border-ink hover:bg-sunken disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent"
                >
                  <span className="flex items-center justify-between gap-2 text-sm font-medium">
                    {item.name}
                    <span className="font-mono text-[11px] text-ink-3">
                      {running ? `step ${(scenario?.step ?? 0) + 1}/${item.steps.length}` : `${item.steps.length} events ▶`}
                    </span>
                  </span>
                  <span className="block text-xs text-ink-3">{item.description}</span>
                  <span className="mt-1 block font-mono text-[11px] text-ink-2">
                    {item.steps.map((s, i) => (
                      <span key={`${s.type}-${i}`} className={running && i === scenario?.step ? "text-signal" : ""}>
                        {i > 0 && " → "}
                        {s.type}
                      </span>
                    ))}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">Single events</p>
          <div className="flex flex-wrap gap-1.5">
            {eventTypes.map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => send(type, EVENT_PRESETS[type] ?? {})}
                disabled={disabled || busy}
                title={JSON.stringify(EVENT_PRESETS[type] ?? {})}
                className={`rounded-[var(--radius-control)] border bg-surface px-2.5 py-1 font-mono text-xs text-ink transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${toneFor(type)}`}
              >
                {sending === type ? "sending…" : humanize(type)}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-ink-3">
            <span className="text-awake">Amber</span> = critical (wakes the agent) ·{" "}
            <span className="text-done">green</span> = terminal (ends the order).
          </p>
        </div>

        <form onSubmit={sendCustom} className="flex flex-col gap-2 border-t border-rule pt-4">
          <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">Custom / unknown event</p>
          <TextInput aria-label="Event type" className="font-mono" value={customType} onChange={(e) => setCustomType(e.target.value)} pattern="[a-z0-9_]+" />
          <TextArea aria-label="Event payload (JSON)" rows={2} className="font-mono text-xs" value={customPayload} onChange={(e) => setCustomPayload(e.target.value)} />
          <Button type="submit" size="sm" disabled={disabled || busy || !customType.trim()} busy={sending === customType.trim()}>
            Send custom event
          </Button>
        </form>
      </div>
    </Panel>
  );
}
