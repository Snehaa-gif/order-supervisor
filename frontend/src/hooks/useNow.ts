"use client";

import { useEffect, useState } from "react";

/** Current time in ms, re-rendering every `intervalMs` (for countdowns and "x ago" labels). */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);

  return now;
}
