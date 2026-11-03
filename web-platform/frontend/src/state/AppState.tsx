import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api } from '../lib/api';
import { chartTheme, SERIES, type ChartTheme, type ThemeName } from '../lib/chartTheme';
import { readStore, writeStore } from '../lib/hooks';
import type { Capabilities, Comparison, DatasetSummary, Dimension, FilterOptions, Filters } from '../lib/types';

export const DIMENSIONS: Dimension[] = ['region', 'state', 'city', 'category', 'subcategory', 'product',
  'customer_segment', 'business_unit', 'channel', 'customer'];

export const EMPTY_FILTERS: Filters = {
  start_date: null, end_date: null, region: [], state: [], city: [], category: [], subcategory: [], product: [],
  customer_segment: [], business_unit: [], channel: [], customer: [], comparison: 'previous_period',
};

export interface Prefs {
  themePref: 'light' | 'dark' | 'system';
  defaultRange: 'latest_year' | 'all';
  comparison: Comparison;
  compactNumbers: boolean;
}

const DEFAULT_PREFS: Prefs = { themePref: 'system', defaultRange: 'latest_year', comparison: 'previous_period', compactNumbers: true };

interface Toast { id: number; message: string; kind: 'info' | 'success' | 'error' }

interface AppStateValue {
  datasets: DatasetSummary[];
  datasetsLoaded: boolean;
  reloadDatasets: () => Promise<DatasetSummary[]>;
  dataset: DatasetSummary | null;
  setDatasetId: (id: number) => void;
  caps: Capabilities | null;
  options: FilterOptions | null;
  filters: Filters;
  setFilters: (f: Filters | ((prev: Filters) => Filters)) => void;
  patchFilters: (patch: Partial<Filters>) => void;
  toggleFilter: (dim: Dimension, value: string) => void;
  setDimension: (dim: Dimension, values: string[]) => void;
  resetFilters: () => void;
  defaultFilters: Filters;
  activeFilterCount: number;
  theme: ThemeName;
  chart: ChartTheme;
  prefs: Prefs;
  setPrefs: (p: Partial<Prefs>) => void;
  colorFor: (dim: string, value: string) => string;
  dimLabel: (dim: string) => string;
  toasts: Toast[];
  toast: (message: string, kind?: Toast['kind']) => void;
  dismissToast: (id: number) => void;
}

const Ctx = createContext<AppStateValue | null>(null);

function systemDark() {
  try { return window.matchMedia('(prefers-color-scheme: dark)').matches; } catch { return false; }
}

// Hierarchy children are cleared when a parent filter changes (region → state → city, category → product).
const CHILDREN: Partial<Record<Dimension, Dimension[]>> = {
  region: ['state', 'city'], state: ['city'], category: ['subcategory', 'product'], subcategory: ['product'],
};

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefsState] = useState<Prefs>(() => ({ ...DEFAULT_PREFS, ...readStore<Partial<Prefs>>('meridian.prefs', {}) }));
  const [sysDark, setSysDark] = useState(systemDark);
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [datasetsLoaded, setLoaded] = useState(false);
  const [datasetId, setDatasetIdState] = useState<number | null>(() => readStore<number | null>('meridian.dataset', null));
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [options, setOptions] = useState<FilterOptions | null>(null);
  const [filters, setFiltersState] = useState<Filters>(EMPTY_FILTERS);
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    let mq: MediaQueryList | null = null;
    try { mq = window.matchMedia('(prefers-color-scheme: dark)'); } catch { return; }
    const on = () => setSysDark(mq!.matches);
    mq.addEventListener('change', on);
    return () => mq!.removeEventListener('change', on);
  }, []);

  const theme: ThemeName = prefs.themePref === 'system' ? (sysDark ? 'dark' : 'light') : prefs.themePref;
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('meridian.theme', prefs.themePref === 'system' ? '' : prefs.themePref); } catch { /* ignore */ }
  }, [theme, prefs.themePref]);

  const setPrefs = useCallback((p: Partial<Prefs>) => {
    setPrefsState((prev) => { const next = { ...prev, ...p }; writeStore('meridian.prefs', next); return next; });
  }, []);

  const toast = useCallback((message: string, kind: Toast['kind'] = 'info') => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 7000 : 4000);
  }, []);
  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  const reloadDatasets = useCallback(async () => {
    try {
      const list = await api.datasets();
      setDatasets(list);
      return list;
    } catch (e) {
      toast(`Could not load datasets: ${(e as Error).message}`, 'error');
      return [];
    } finally { setLoaded(true); }
  }, [toast]);

  useEffect(() => { void reloadDatasets(); }, [reloadDatasets]);

  const ready = datasets.filter((d) => d.status === 'ready');
  const dataset = ready.find((d) => d.id === datasetId) ?? ready.find((d) => d.is_default) ?? ready[0] ?? null;

  const setDatasetId = useCallback((id: number) => { setDatasetIdState(id); writeStore('meridian.dataset', id); }, []);

  const defaultFilters = useMemo<Filters>(() => {
    const base = { ...EMPTY_FILTERS, comparison: prefs.comparison };
    const y = options?.latest_full_year;
    if (prefs.defaultRange === 'latest_year' && y && (options?.years?.length ?? 0) >= 2) {
      return { ...base, start_date: `${y}-01-01`, end_date: `${y}-12-31` };
    }
    return base;
  }, [options, prefs.defaultRange, prefs.comparison]);

  // Load capabilities + filter options whenever the active dataset changes, then restore saved filters.
  useEffect(() => {
    if (!dataset) { setCaps(null); setOptions(null); return; }
    let cancelled = false;
    Promise.all([api.capabilities(dataset.id), api.filterOptions(dataset.id)]).then(([c, o]) => {
      if (cancelled) return;
      setCaps(c);
      setOptions(o);
      const saved = readStore<Filters | null>(`meridian.filters.${dataset.id}.v${dataset.updated_at}`, null);
      if (saved) { setFiltersState({ ...EMPTY_FILTERS, ...saved }); return; }
      const y = o.latest_full_year;
      const base = { ...EMPTY_FILTERS, comparison: prefs.comparison };
      setFiltersState(prefs.defaultRange === 'latest_year' && y && (o.years?.length ?? 0) >= 2
        ? { ...base, start_date: `${y}-01-01`, end_date: `${y}-12-31` } : base);
    }).catch((e) => toast(`Could not load dataset metadata: ${(e as Error).message}`, 'error'));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataset?.id, dataset?.updated_at]);

  const setFilters = useCallback((f: Filters | ((prev: Filters) => Filters)) => {
    setFiltersState((prev) => {
      const next = typeof f === 'function' ? f(prev) : f;
      if (dataset) writeStore(`meridian.filters.${dataset.id}.v${dataset.updated_at}`, next);
      return next;
    });
  }, [dataset]);

  const patchFilters = useCallback((patch: Partial<Filters>) => setFilters((p) => ({ ...p, ...patch })), [setFilters]);

  const setDimension = useCallback((dim: Dimension, values: string[]) => {
    setFilters((p) => {
      const next = { ...p, [dim]: values };
      for (const c of CHILDREN[dim] ?? []) {
        // keep child selections that still belong to the selected parents
        const link = options?.links[c];
        if (values.length === 0 || !link) continue;
        next[c] = next[c].filter((v) => {
          const parent = link.map[v];
          return link.parent === dim ? values.includes(parent) : true;
        });
      }
      return next;
    });
  }, [setFilters, options]);

  const toggleFilter = useCallback((dim: Dimension, value: string) => {
    setFilters((p) => {
      const cur = p[dim];
      const values = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
      return { ...p, [dim]: values };
    });
  }, [setFilters]);

  const resetFilters = useCallback(() => setFilters(defaultFilters), [setFilters, defaultFilters]);

  const activeFilterCount = DIMENSIONS.reduce((n, d) => n + (filters[d].length ? 1 : 0), 0);

  const chart = useMemo(() => chartTheme(theme), [theme]);

  const colorFor = useCallback((dim: string, value: string) => {
    if (value === 'Other') return chart.muted;
    const vals = options?.dimensions[dim]?.values ?? [];
    if (vals.length > 8) return chart.series[0];
    const idx = vals.indexOf(value);
    return SERIES[theme][idx >= 0 ? idx % 8 : 0];
  }, [options, theme, chart]);

  const dimLabel = useCallback((dim: string) => caps?.filters[dim]?.label ?? options?.dimensions[dim]?.label ?? dim, [caps, options]);

  const value: AppStateValue = {
    datasets, datasetsLoaded, reloadDatasets, dataset, setDatasetId, caps, options, filters, setFilters, patchFilters,
    toggleFilter, setDimension, resetFilters, defaultFilters, activeFilterCount, theme, chart, prefs, setPrefs, colorFor,
    dimLabel, toasts, toast, dismissToast,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppStateValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApp must be used inside AppStateProvider');
  return v;
}

/** Deepest active level of a geographic / product hierarchy → the level a chart should show. */
export function drillLevel(filters: Filters, chain: Dimension[], available: (d: Dimension) => boolean): Dimension {
  const usable = chain.filter(available);
  let level = usable[0];
  for (let i = 0; i < usable.length - 1; i++) {
    if (filters[usable[i]].length === 1) level = usable[i + 1];
    else break;
  }
  return level;
}
