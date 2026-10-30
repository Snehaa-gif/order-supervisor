"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, api, errorMessage, type JsonObject, type Supervisor } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextArea, TextInput } from "@/components/ui/Field";
import { ErrorList, Notice } from "@/components/ui/Notice";
import { Panel } from "@/components/ui/Panel";
import { useToast } from "@/components/ui/Toaster";

function randomOrderId(): string {
  return `ORD-${1000 + Math.floor(Math.random() * 9000)}`;
}

interface ContextFields {
  customer: string;
  items: string;
  total: string;
  shipping: string;
  extraJson: string;
}

const DEFAULT_CONTEXT: ContextFields = {
  customer: "Asha Verma",
  items: "Noise-cancelling headphones x1",
  total: "₹2,499",
  shipping: "Standard (3-5 days)",
  extraJson: '{ "customer_tier": "regular", "city": "Bengaluru" }',
};

/** Builds the order context object; returns an error message if the raw JSON is invalid. */
function buildContext(fields: ContextFields): { context?: JsonObject; error?: string } {
  const base: JsonObject = {};
  if (fields.customer.trim()) base.customer_name = fields.customer.trim();
  if (fields.items.trim()) base.items = fields.items.trim();
  if (fields.total.trim()) base.total = fields.total.trim();
  if (fields.shipping.trim()) base.shipping_method = fields.shipping.trim();
  if (!fields.extraJson.trim()) return { context: base };
  try {
    const extra: unknown = JSON.parse(fields.extraJson);
    if (typeof extra !== "object" || extra === null || Array.isArray(extra)) {
      return { error: "Extra context must be a JSON object, e.g. { \"city\": \"Pune\" }" };
    }
    return { context: { ...base, ...(extra as JsonObject) } };
  } catch {
    return { error: "Extra context is not valid JSON." };
  }
}

export function NewRunForm() {
  const router = useRouter();
  const { notify } = useToast();
  const [supervisors, setSupervisors] = useState<Supervisor[]>();
  const [loadError, setLoadError] = useState<string>();
  const [supervisorId, setSupervisorId] = useState("");
  // Generated on the client after mount so server and client render the same HTML.
  const [orderId, setOrderId] = useState("");
  const [fields, setFields] = useState<ContextFields>(DEFAULT_CONTEXT);
  const [instructions, setInstructions] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listSupervisors()
      .finally(() => {
        if (!cancelled) setOrderId((current) => current || randomOrderId());
      })
      .then((list) => {
        if (cancelled) return;
        setSupervisors(list);
        setSupervisorId((current) => current || list[0]?.id || "");
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setField = (key: keyof ContextFields) => (value: string) => setFields((current) => ({ ...current, [key]: value }));
  const selected = supervisors?.find((s) => s.id === supervisorId);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const { context, error } = buildContext(fields);
    if (error || !context) {
      setErrors([error ?? "Invalid order context."]);
      return;
    }
    setBusy(true);
    setErrors([]);
    try {
      const run = await api.startRun({
        supervisor_id: supervisorId,
        order_id: orderId.trim(),
        order_context: context,
        instructions: instructions.split("\n").map((line) => line.trim()).filter(Boolean),
      });
      notify(`Supervisor started for ${run.order_id}`);
      router.push(`/runs/${run.id}`);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setErrors([`${err.message}. Terminate that run first, or use a different order ID.`]);
      } else {
        setErrors(err instanceof ApiError ? err.messages : [errorMessage(err)]);
      }
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]" noValidate>
      <div className="flex flex-col gap-6">
        <Panel title="Order" eyebrow="01 · what to supervise">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Order ID" htmlFor="run-order" hint="Letters, numbers, - and _. One active run per order.">
              <div className="flex gap-2">
                <TextInput id="run-order" className="font-mono" value={orderId} onChange={(e) => setOrderId(e.target.value)} required />
                <Button type="button" variant="ghost" size="md" onClick={() => setOrderId(randomOrderId())} aria-label="Generate a new order ID">
                  ↻
                </Button>
              </div>
            </Field>
            <Field label="Customer name" htmlFor="run-customer">
              <TextInput id="run-customer" value={fields.customer} onChange={(e) => setField("customer")(e.target.value)} />
            </Field>
            <Field label="Items" htmlFor="run-items">
              <TextInput id="run-items" value={fields.items} onChange={(e) => setField("items")(e.target.value)} />
            </Field>
            <Field label="Order total" htmlFor="run-total">
              <TextInput id="run-total" value={fields.total} onChange={(e) => setField("total")(e.target.value)} />
            </Field>
            <Field label="Shipping method" htmlFor="run-shipping">
              <TextInput id="run-shipping" value={fields.shipping} onChange={(e) => setField("shipping")(e.target.value)} />
            </Field>
            <Field label="Extra context (JSON, optional)" htmlFor="run-extra">
              <TextArea id="run-extra" rows={2} className="font-mono text-xs" value={fields.extraJson} onChange={(e) => setField("extraJson")(e.target.value)} />
            </Field>
          </div>
        </Panel>

        <Panel title="Run-specific instructions" eyebrow="02 · optional">
          <Field label="One instruction per line" htmlFor="run-instructions" hint="You can also add instructions while the run is live.">
            <TextArea
              id="run-instructions"
              rows={3}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder={"For this order, prioritize speed over cost.\nIf shipment is delayed, escalate immediately."}
            />
          </Field>
        </Panel>
      </div>

      <div className="flex flex-col gap-4 lg:sticky lg:top-20 lg:h-fit">
        <Panel title="Supervisor" eyebrow="03 · who supervises">
          {loadError && <Notice tone="error">{loadError}</Notice>}
          {!supervisors && !loadError && <p className="text-sm text-ink-3">Loading supervisors…</p>}
          {supervisors && (
            <div className="flex flex-col gap-3">
              <Field label="Supervisor config" htmlFor="run-supervisor">
                <Select id="run-supervisor" value={supervisorId} onChange={(e) => setSupervisorId(e.target.value)}>
                  {supervisors.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </Select>
              </Field>
              {selected && (
                <div className="rounded-[var(--radius-control)] bg-sunken p-3 text-xs leading-relaxed text-ink-2">
                  <p className="line-clamp-5">{selected.base_instruction}</p>
                  <p className="mt-2 font-mono text-ink-3">
                    wakes: {selected.wake_aggressiveness} · default {selected.default_wake_minutes}m · {selected.tools.length} tools
                  </p>
                </div>
              )}
            </div>
          )}
        </Panel>
        <ErrorList messages={errors} />
        <Button type="submit" variant="primary" busy={busy} disabled={!supervisorId || !orderId.trim()}>
          Start supervisor run
        </Button>
      </div>
    </form>
  );
}
