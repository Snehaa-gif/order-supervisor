import type { Supervisor } from "@/lib/api";
import { humanize } from "@/lib/format";

interface SupervisorCardProps {
  supervisor: Supervisor;
}

export function SupervisorCard({ supervisor }: SupervisorCardProps) {
  return (
    <article className="flex flex-col gap-3 rounded-[var(--radius-panel)] border border-rule bg-surface p-5 transition-shadow hover:shadow-raised">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold tracking-tight">{supervisor.name}</h3>
          <p className="font-mono text-[11px] text-ink-3">{supervisor.id}</p>
        </div>
        {supervisor.is_template && (
          <span className="rounded-full border border-rule-strong px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-ink-2">
            Template
          </span>
        )}
      </header>
      <p className="line-clamp-4 text-sm leading-relaxed text-ink-2">{supervisor.base_instruction}</p>
      <dl className="grid grid-cols-3 gap-2 border-t border-rule pt-3 font-mono text-xs">
        <Fact label="Default wake" value={`${supervisor.default_wake_minutes} min`} />
        <Fact label="Max sleep" value={`${supervisor.max_sleep_minutes} min`} />
        <Fact label="Wake-ups" value={humanize(supervisor.wake_aggressiveness)} />
      </dl>
      <ul className="flex flex-wrap gap-1.5" aria-label="Enabled tools">
        {supervisor.tools.map((tool) => (
          <li key={tool} className="rounded-[4px] bg-sunken px-2 py-0.5 font-mono text-[11px] text-ink-2">
            {tool}
          </li>
        ))}
      </ul>
      {supervisor.model && <p className="font-mono text-[11px] text-ink-3">model: {supervisor.model}</p>}
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.12em] text-ink-3">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </div>
  );
}
