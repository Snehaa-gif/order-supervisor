import { NewRunForm } from "@/components/runs/NewRunForm";

export default function NewRunPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">New run</p>
        <h1 className="text-3xl font-semibold tracking-tight">Start supervising an order</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          This starts one Temporal workflow for the order. The agent takes its first turn immediately, then sleeps until
          something important happens.
        </p>
      </div>
      <NewRunForm />
    </div>
  );
}
