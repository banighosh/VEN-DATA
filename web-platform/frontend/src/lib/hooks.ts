import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

/* ------------------------------------------------------------------ routing (hash based, no deps) */
export type Page =
  | 'dashboard' | 'executive' | 'performance' | 'financial' | 'customers' | 'products' | 'regional'
  | 'operations' | 'insights' | 'explorer' | 'data' | 'settings';

const PAGES: Page[] = ['dashboard', 'executive', 'performance', 'financial', 'customers', 'products', 'regional',
  'operations', 'insights', 'explorer', 'data', 'settings'];

function readHash(): Page {
  const raw = window.location.hash.replace(/^#\/?/, '').split('?')[0] as Page;
  return PAGES.includes(raw) ? raw : 'dashboard';
}

const subscribeHash = (cb: () => void) => { window.addEventListener('hashchange', cb); return () => window.removeEventListener('hashchange', cb); };

export function useRoute(): Page {
  return useSyncExternalStore(subscribeHash, readHash, () => 'dashboard' as Page);
}

export function navigate(page: Page) {
  if (readHash() !== page) window.location.hash = `/${page}`;
  document.getElementById('main-scroll')?.scrollTo({ top: 0 });
}

/* ------------------------------------------------------------------ data fetching */
export interface AsyncState<T> { data: T | undefined; error: Error | undefined; loading: boolean; reload: () => void }

/**
 * Fetch with abort-on-change. While a refetch runs the previous data stays on
 * screen (charts keep their frame) and `loading` is true.
 */
export function useAsync<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[], enabled = true): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (!enabled) { setLoading(false); return; }
    const ctrl = new AbortController();
    setLoading(true);
    fnRef.current(ctrl.signal)
      .then((d) => { if (!ctrl.signal.aborted) { setData(d); setError(undefined); } })
      .catch((e: Error) => { if (!ctrl.signal.aborted && e.name !== 'AbortError') setError(e); })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick, enabled]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

/* ------------------------------------------------------------------ safe localStorage */
export function readStore<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch { return fallback; }
}

export function writeStore(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

export function useClickOutside(ref: React.RefObject<HTMLElement | null>, onOutside: () => void, active = true) {
  useEffect(() => {
    if (!active) return;
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onOutside(); };
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onOutside(); };
    document.addEventListener('mousedown', handler);
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('mousedown', handler); document.removeEventListener('keydown', key); };
  }, [ref, onOutside, active]);
}
