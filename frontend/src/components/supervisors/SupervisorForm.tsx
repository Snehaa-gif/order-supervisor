"use client";

import { useState, type FormEvent } from "react";
import { ApiError, api, type Meta, type Supervisor, type WakeAggressiveness } from "@/lib/api";
import { humanize } from "@/lib/format";
import { Button } from "@/components/ui/Button";
import { Field, Select, TextArea, TextInput } from "@/components/ui/Field";
import { ErrorList } from "@/components/ui/Notice";
import { useToast } from "@/components/ui/Toaster";

const AGGRESSIVENESS_HELP: Record<WakeAggressiveness, string> = {
  low: "Only critical events (failed payments, delays, refunds, customer messages) wake the agent.",
  balanced: "Critical events plus orders that have gone quiet for 24h+.",
  high: "Every event wakes the agent immediately.",
};

interface SupervisorFormProps {
  meta: Meta;
  onCreated: (supervisor: Supervisor) => void;
}

export function SupervisorForm({ meta, onCreated }: SupervisorFormProps) {
  const { notify } = useToast();
  const [name, setName] = useState("");
  const [instruction, setInstruction] = useState("");
  const [tools, setTools] = useState<string[]>(meta.action_tools.map((tool) => tool.name));
  const [defaultWake, setDefaultWake] = useState(5);
  const [maxSleep, setMaxSleep] = useState(60);
  const [aggressiveness, setAggressiveness] = useState<WakeAggressiveness>("balanced");
  const [model, setModel] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const toggleTool = (toolName: string) =>
    setTools((current) => (current.includes(toolName) ? current.filter((t) => t !== toolName) : [...current, toolName]));

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      const created = await api.createSupervisor({
        name: name.trim(),
        base_instruction: instruction.trim(),
        tools,
        default_wake_minutes: defaultWake,
        max_sleep_minutes: maxSleep,
        wake_aggressiveness: aggressiveness,
        model: model.trim() || null,
      });
      notify(`Supervisor "${created.name}" created`);
      setName("");
      setInstruction("");
      setModel("");
      onCreated(created);
    } catch (error: unknown) {
      setErrors(error instanceof ApiError ? error.messages : ["Could not create the supervisor."]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <Field label="Name" htmlFor="sup-name">
        <TextInput id="sup-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Festive Season Supervisor" required maxLength={120} />
      </Field>

      <Field label="Base instruction" htmlFor="sup-instruction" hint="The supervisor's standing orders. At least 10 characters.">
        <TextArea
          id="sup-instruction"
          rows={5}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="Keep the customer informed about anything that affects them, escalate payment problems to the payments team…"
          required
        />
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1.5 text-[13px] font-medium">Available action tools</legend>
        {meta.action_tools.map((tool) => (
          <label
            key={tool.name}
            className="flex cursor-pointer items-start gap-3 rounded-[var(--radius-control)] border border-rule px-3 py-2 transition-colors hover:border-rule-strong has-[:checked]:border-ink has-[:checked]:bg-paper"
          >
            <input type="checkbox" className="mt-1 accent-[var(--signal)]" checked={tools.includes(tool.name)} onChange={() => toggleTool(tool.name)} />
            <span>
              <span className="block font-mono text-[13px] text-ink">{tool.name}</span>
              <span className="block text-xs text-ink-3">{tool.description}</span>
            </span>
          </label>
        ))}
        <p className="text-xs text-ink-3">
          Control tools ({meta.control_tools.map((tool) => tool.name).join(", ")}) are always available.
        </p>
      </fieldset>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Default wake (min)" htmlFor="sup-default-wake" hint="Used when the agent doesn't pick a time.">
          <TextInput id="sup-default-wake" type="number" min={1} value={defaultWake} onChange={(e) => setDefaultWake(Number(e.target.value))} />
        </Field>
        <Field label="Max sleep (min)" htmlFor="sup-max-sleep" hint="Longest the agent may sleep.">
          <TextInput id="sup-max-sleep" type="number" min={1} value={maxSleep} onChange={(e) => setMaxSleep(Number(e.target.value))} />
        </Field>
      </div>

      <Field label="Wake-up aggressiveness" htmlFor="sup-aggr" hint={AGGRESSIVENESS_HELP[aggressiveness]}>
        <Select id="sup-aggr" value={aggressiveness} onChange={(e) => setAggressiveness(e.target.value as WakeAggressiveness)}>
          {meta.wake_aggressiveness.map((level) => (
            <option key={level} value={level}>
              {humanize(level)}
            </option>
          ))}
        </Select>
      </Field>

      <Field label="Model (optional)" htmlFor="sup-model" hint="Leave blank to use the server default.">
        <TextInput id="sup-model" value={model} onChange={(e) => setModel(e.target.value)} placeholder="gemini-3.5-flash" />
      </Field>

      <ErrorList messages={errors} />
      <Button type="submit" variant="primary" busy={busy}>
        Create supervisor
      </Button>
    </form>
  );
}
