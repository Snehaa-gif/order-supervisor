import { Suspense } from "react";
import { RunDetailView } from "@/components/runs/RunDetailView";

export default function RunPage() {
  return (
    <Suspense fallback={<p className="text-sm text-ink-3">Loading run…</p>}>
      <RunDetailView />
    </Suspense>
  );
}
