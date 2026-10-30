"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface PollingState<T> {
  data: T | undefined;
  error: Error | undefined;
  isLoading: boolean;
  refresh: () => Promise<void>;
}

/**
 * Fetches `load` immediately and then every `intervalMs` while `enabled` is true.
 * Requests never overlap: the next one is scheduled only after the previous finishes.
 */
export function usePolling<T>(load: () => Promise<T>, intervalMs: number, enabled = true): PollingState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [isLoading, setIsLoading] = useState(true);
  const loadRef = useRef(load);
  const mountedRef = useRef(true);

  useEffect(() => {
    loadRef.current = load;
  }, [load]);

  const refresh = useCallback(async () => {
    try {
      const next = await loadRef.current();
      if (!mountedRef.current) return;
      setData(next);
      setError(undefined);
    } catch (err: unknown) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err : new Error("Request failed"));
    } finally {
      if (mountedRef.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const tick = async () => {
      await refresh();
      if (!cancelled && enabled) timer = setTimeout(tick, intervalMs);
    };
    timer = setTimeout(tick, 0);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [refresh, intervalMs, enabled]);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return { data, error, isLoading, refresh };
}
