import type { FinalReport } from "@/lib/api";

interface FinalReportPanelProps {
  report: FinalReport;
  closeReason: string | null;
}

/** End-of-run output: shown prominently at the top once a run closes. */
export function FinalReportPanel({ report, closeReason }: FinalReportPanelProps) {
  return (
    <section aria-labelledby="final-report-heading" className="animate-enter overflow-hidden rounded-[var(--radius-panel)] border border-ink bg-surface shadow-raised">
      <header className="flex flex-wrap items-baseline justify-between gap-3 bg-ink px-6 py-4 text-paper">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-paper/60">End-of-run report</p>
          <h2 id="final-report-heading" className="text-xl font-semibold tracking-tight">
            {report.outcome}
          </h2>
        </div>
        {closeReason && <p className="max-w-md text-right text-xs text-paper/70">Closed because: {closeReason}</p>}
      </header>
      <div className="grid gap-6 px-6 py-5 lg:grid-cols-[1.3fr_1fr]">
        <div className="flex flex-col gap-4">
          <p className="text-[15px] leading-relaxed text-ink">{report.summary}</p>
          <ReportList title="Key actions" items={report.key_actions} marker="bg-sleeping" />
        </div>
        <div className="flex flex-col gap-4 border-rule lg:border-l lg:pl-6">
          <ReportList title="Learnings" items={report.learnings} marker="bg-done" />
          <ReportList title="Recommendations" items={report.recommendations} marker="bg-signal" />
        </div>
      </div>
    </section>
  );
}

function ReportList({ title, items, marker }: { title: string; items: string[]; marker: string }) {
  return (
    <div>
      <h3 className="mb-2 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">{title}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-ink-3">None recorded.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {items.map((item, index) => (
            <li key={`${index}-${item}`} className="flex gap-2.5 text-sm leading-relaxed text-ink-2">
              <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${marker}`} aria-hidden />
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
