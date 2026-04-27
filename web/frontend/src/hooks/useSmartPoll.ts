import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Smart polling hook with visibility guards and state-aware auto-stop.
 *
 * - `enabled: false` → immediately stops polling, no fetches
 * - `stopWhen(data)` returning true → auto-disables
 * - Immediate first fetch when enabled (no waiting for interval)
 * - Interval changes do NOT restart the polling cycle (avoids churn)
 * - Proper cleanup on unmount or when enabled changes
 * - Returns null data when fetcher returns null (304 no change)
 */
export interface SmartPollOptions<T> {
  /** Async function that fetches data. Return null to signal "no change" (e.g. 304). */
  fetcher: () => Promise<T | null>;
  /** Polling interval in milliseconds. */
  interval: number;
  /** Master on/off switch. When false, polling stops immediately. */
  enabled: boolean;
  /** Auto-stop condition. If provided and returns true, polling stops. */
  stopWhen?: (data: T) => boolean;
}

export interface SmartPollResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  /** Manually trigger a fetch outside the polling cycle. */
  refresh: () => void;
}

export function useSmartPoll<T>({
  fetcher,
  interval,
  enabled,
  stopWhen,
}: SmartPollOptions<T>): SmartPollResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [stopped, setStopped] = useState(false);

  // Store mutable values in refs to avoid effect re-triggers
  const fetcherRef = useRef(fetcher);
  const stopWhenRef = useRef(stopWhen);
  const intervalRef = useRef(interval);

  fetcherRef.current = fetcher;
  stopWhenRef.current = stopWhen;
  intervalRef.current = interval;

  // Reset stopped state when enabled changes to true
  useEffect(() => {
    if (enabled) {
      setStopped(false);
    }
  }, [enabled]);

  const doFetch = useCallback(async () => {
    try {
      setError(null);
      const result = await fetcherRef.current();
      if (result !== null) {
        setData(result);
        setLoading(false);
        // Check auto-stop condition
        if (stopWhenRef.current && stopWhenRef.current(result)) {
          setStopped(true);
        }
      } else {
        // 304 — no change, don't update data or trigger re-renders
        setLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled || stopped) return;

    // Immediate first fetch
    setLoading(true);
    doFetch();

    // Use a self-scheduling timeout instead of setInterval so that
    // interval changes (via ref) take effect on the next tick without
    // tearing down/recreating the cycle.
    let timeoutId: ReturnType<typeof setTimeout>;
    let cancelled = false;

    const schedule = () => {
      if (cancelled) return;
      timeoutId = setTimeout(async () => {
        if (cancelled) return;
        await doFetch();
        schedule();
      }, intervalRef.current);
    };

    schedule();

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [enabled, stopped, doFetch]);

  return { data, loading, error, refresh: doFetch };
}
