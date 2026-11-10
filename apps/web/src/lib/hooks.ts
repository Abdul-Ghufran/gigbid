import { useCallback, useEffect, useRef, useState } from "react";

/** Load data with loading / error state and optional polling (keeps showing stale data while refreshing). */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async () => {
    try { setData(await fnRef.current()); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    setLoading(true);
    reload();
    if (!pollMs) return;
    const t = setInterval(reload, pollMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error, loading, reload, setData };
}

export const money = (n?: number | null, hourly = false) =>
  n == null ? "-" : `$${n.toLocaleString(undefined, { maximumFractionDigits: hourly ? 1 : 0 })}${hourly ? "/h" : ""}`;
export const pct = (n?: number | null) => (n == null ? "-" : `${Math.round(n * 100)}%`);
