import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";

export interface Loaded<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  reload: () => void;
}

/** GET `path` (skipped while null), re-fetching when it changes. */
export function useApi<T>(path: string | null, pollMs?: number): Loaded<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    setLoading(true);
    api<T>(path)
      .then((value) => !cancelled && (setData(value), setError(undefined)))
      .catch((err: Error) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  const reloadRef = useRef(reload);
  reloadRef.current = reload;
  useEffect(() => {
    if (!pollMs) return;
    const id = window.setInterval(() => reloadRef.current(), pollMs);
    return () => window.clearInterval(id);
  }, [pollMs]);

  return { data, error, loading, reload };
}

/** Wrap an async action with pending/error state for buttons and forms. */
export function useAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const run = useCallback(
    async (...args: A): Promise<R | undefined> => {
      setPending(true);
      setError(undefined);
      try {
        return await fn(...args);
      } catch (err) {
        setError((err as Error).message);
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [fn],
  );
  return { run, pending, error, clearError: () => setError(undefined) };
}
