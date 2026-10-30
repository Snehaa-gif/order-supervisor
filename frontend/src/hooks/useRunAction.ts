"use client";

import { useCallback, useState } from "react";
import { useToast } from "@/components/ui/Toaster";
import { errorMessage, type Accepted } from "@/lib/api";

export interface RunActionApi {
  /** Key of the action currently in flight, if any (used to show a spinner on the right button). */
  pending: string | null;
  perform: (key: string, action: () => Promise<Accepted>) => Promise<boolean>;
}

/** Runs a mutation against a live run, toasts the outcome, and refreshes the run immediately. */
export function useRunAction(refresh: () => Promise<void>): RunActionApi {
  const { notify } = useToast();
  const [pending, setPending] = useState<string | null>(null);

  const perform = useCallback(
    async (key: string, action: () => Promise<Accepted>) => {
      setPending(key);
      try {
        const result = await action();
        notify(result.message, "success");
        await refresh();
        return true;
      } catch (error: unknown) {
        notify(errorMessage(error), "error");
        return false;
      } finally {
        setPending(null);
      }
    },
    [notify, refresh],
  );

  return { pending, perform };
}
