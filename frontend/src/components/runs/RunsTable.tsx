"use client";

import Link from "next/link";
import { useNow } from "@/hooks/useNow";
import type { Run } from "@/lib/api";
import { formatRelative, humanize } from "@/lib/format";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { WakeState } from "@/components/runs/WakeState";

interface RunsTableProps {
  runs: Run[];
  variant: "active" | "closed";
}

export function RunsTable({ runs, variant }: RunsTableProps) {
  const now = useNow(5000);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-rule font-mono text-[11px] uppercase tracking-[0.12em] text-ink-3">
            <th scope="col" className="py-2 pr-4 font-normal">Order</th>
            <th scope="col" className="py-2 pr-4 font-normal">Supervisor</th>
            <th scope="col" className="py-2 pr-4 font-normal">Run status</th>
            <th scope="col" className="py-2 pr-4 font-normal">Order status</th>
            <th scope="col" className="py-2 pr-4 font-normal">{variant === "active" ? "Agent" : "Outcome"}</th>
            <th scope="col" className="py-2 pr-4 text-right font-normal">Turns</th>
            <th scope="col" className="py-2 text-right font-normal">Updated</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="group border-b border-rule last:border-b-0 hover:bg-paper">
              <td className="py-3 pr-4">
                <Link
                  href={`/runs/${run.id}`}
                  className="font-mono font-medium text-ink underline-offset-4 group-hover:text-signal group-hover:underline"
                >
                  {run.order_id}
                </Link>
              </td>
              <td className="py-3 pr-4 text-ink-2">{run.supervisor_name}</td>
              <td className="py-3 pr-4">
                <StatusBadge status={run.status} />
              </td>
              <td className="py-3 pr-4 text-ink-2">{humanize(run.order_status)}</td>
              <td className="max-w-[280px] truncate py-3 pr-4">
                {variant === "active" ? (
                  <WakeState status={run.status} nextWakeAt={run.next_wake_at} />
                ) : (
                  <span className="text-xs text-ink-2">{run.final_report?.outcome ?? run.close_reason ?? "—"}</span>
                )}
              </td>
              <td className="py-3 pr-4 text-right font-mono text-ink-2">{run.turn_count}</td>
              <td className="py-3 text-right font-mono text-xs text-ink-3">{formatRelative(run.updated_at, now)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
