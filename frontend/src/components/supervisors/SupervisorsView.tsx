"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage, type Meta, type Supervisor } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";
import { EmptyState, Notice } from "@/components/ui/Notice";
import { SupervisorCard } from "@/components/supervisors/SupervisorCard";
import { SupervisorForm } from "@/components/supervisors/SupervisorForm";

export function SupervisorsView() {
  const [supervisors, setSupervisors] = useState<Supervisor[]>();
  const [meta, setMeta] = useState<Meta>();
  const [error, setError] = useState<string>();

  const load = useCallback(async () => {
    try {
      const [list, options] = await Promise.all([api.listSupervisors(), api.meta()]);
      setSupervisors(list);
      setMeta(options);
      setError(undefined);
    } catch (err: unknown) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(load, 0);
    return () => clearTimeout(timer);
  }, [load]);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">Configuration</p>
        <h1 className="text-3xl font-semibold tracking-tight">Supervisors</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          A supervisor is a reusable setup: standing instructions, the tools it may use, and how eagerly it wakes up.
          Every run starts from one.
        </p>
      </div>

      {error && <Notice tone="error">{error}</Notice>}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_420px]">
        <section aria-label="Supervisor list" className="flex flex-col gap-4">
          {!supervisors && !error && <p className="text-sm text-ink-3">Loading supervisors…</p>}
          {supervisors?.length === 0 && <EmptyState title="No supervisors yet" />}
          <div className="grid gap-4 xl:grid-cols-2">
            {supervisors?.map((supervisor) => (
              <SupervisorCard key={supervisor.id} supervisor={supervisor} />
            ))}
          </div>
        </section>

        <Panel title="New supervisor" eyebrow="create" className="h-fit lg:sticky lg:top-20">
          {meta ? (
            <SupervisorForm meta={meta} onCreated={(created) => setSupervisors((current) => [...(current ?? []), created])} />
          ) : (
            <p className="text-sm text-ink-3">Loading options…</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
