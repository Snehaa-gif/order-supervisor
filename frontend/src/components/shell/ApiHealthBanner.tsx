"use client";

import { usePolling } from "@/hooks/usePolling";
import { API_URL, api } from "@/lib/api";

const HEALTH_CHECK_INTERVAL_MS = 10_000;

/** Shows a thin warning strip whenever the backend stops answering. */
export function ApiHealthBanner() {
  const { error } = usePolling(api.health, HEALTH_CHECK_INTERVAL_MS);
  if (!error) return null;
  return (
    <div role="alert" className="border-b border-stopped/30 bg-stopped-wash px-6 py-2 text-center text-sm text-stopped">
      Backend unreachable at <span className="font-mono">{API_URL}</span>. Start it with{" "}
      <span className="font-mono">uv run uvicorn app.main:app --port 8000</span>. Retrying…
    </div>
  );
}
