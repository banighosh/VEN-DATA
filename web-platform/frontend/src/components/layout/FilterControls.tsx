import { CalendarRange, Check, ChevronDown, Search, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fmtDate } from '../../lib/format';
import { useClickOutside } from '../../lib/hooks';
import type { Comparison, Dimension, Filters } from '../../lib/types';
import { useApp } from '../../state/AppState';
import { Button, cx } from '../ui/primitives';

/* ------------------------------------------------------------------ dimension multi-select */
export function MultiSelect({ dim }: { dim: Dimension }) {
  const { options, filters, setDimension, dimLabel, caps } = useApp();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => { setOpen(false); setQ(''); }, []);
  useClickOutside(ref, close, open);
  const all = options?.dimensions[dim]?.values ?? [];
  const link = options?.links[dim];
  // Cascade: when the parent level is filtered, only offer children that belong to it.
  const parentSel = link ? filters[link.parent as Dimension] : [];
  const values = useMemo(() => {
    let v = all;
    if (link && parentSel.length) v = v.filter((x) => parentSel.includes(link.map[x]));
    if (q) v = v.filter((x) => x.toLowerCase().includes(q.toLowerCase()));
    return v;
  }, [all, link, parentSel, q]);
  const selected = filters[dim];
  const available = caps?.filters[dim]?.available;
  if (!available) return null;
  const label = dimLabel(dim);
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}
        className={cx('inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-sm',
          selected.length ? 'border-accent/50 bg-accent-soft text-accent-ink' : 'border-line-strong bg-panel text-ink hover:bg-panel-2')}>
        <span className={selected.length ? 'font-medium' : 'text-ink-2'}>{label}</span>
        {selected.length > 0 && <span className="max-w-[120px] truncate font-medium">{selected.length === 1 ? selected[0] : `${selected.length} selected`}</span>}
        <ChevronDown size={14} className="opacity-60" />
      </button>
      {open && (
        <div className="absolute left-0 top-10 z-40 w-64 rounded-lg border border-line bg-panel shadow-pop">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2">
            <Search size={14} className="text-ink-3" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${label.toLowerCase()}`}
              className="w-full bg-transparent text-sm outline-none placeholder:text-ink-3" />
          </div>
          <ul role="listbox" aria-multiselectable="true" className="scroll-thin max-h-64 overflow-y-auto p-1">
            {values.length === 0 && <li className="px-2 py-3 text-center text-xs text-ink-3">No matches</li>}
            {values.map((v) => {
              const on = selected.includes(v);
              return (
                <li key={v} role="option" aria-selected={on}>
                  <button onClick={() => setDimension(dim, on ? selected.filter((x) => x !== v) : [...selected, v])}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-panel-2">
                    <span className={cx('flex h-4 w-4 shrink-0 items-center justify-center rounded border', on ? 'border-accent bg-accent text-white' : 'border-line-strong')}>
                      {on && <Check size={12} strokeWidth={3} />}
                    </span>
                    <span className="truncate">{v}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="flex items-center justify-between border-t border-line px-3 py-2 text-xs">
            <span className="text-ink-3">{selected.length} of {all.length} selected</span>
            <div className="flex gap-1">
              {selected.length > 0 && <Button size="sm" variant="ghost" onClick={() => setDimension(dim, [])}>Clear</Button>}
              <Button size="sm" variant="primary" onClick={close}>Done</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ date range */
interface PresetRange { id: string; label: string; start: string | null; end: string | null }

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export function useDatePresets(): PresetRange[] {
  const { options } = useApp();
  return useMemo(() => {
    const out: PresetRange[] = [{ id: 'all', label: 'All time', start: null, end: null }];
    if (!options?.date_max) return out;
    const max = new Date(`${options.date_max}T00:00:00`);
    const y = max.getFullYear(), m = max.getMonth();
    const monthStart = new Date(y, m, 1), monthEnd = new Date(y, m + 1, 0);
    const q = Math.floor(m / 3);
    out.push({ id: 'last-month', label: `Latest month (${monthStart.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })})`, start: iso(monthStart), end: iso(monthEnd) });
    out.push({ id: 'last-quarter', label: `Latest quarter (Q${q + 1} ${y})`, start: iso(new Date(y, q * 3, 1)), end: iso(new Date(y, q * 3 + 3, 0)) });
    out.push({ id: 'ytd', label: `Year to date (${y})`, start: `${y}-01-01`, end: options.date_max });
    out.push({ id: 'l12m', label: 'Last 12 months of data', start: iso(new Date(y, m - 11, 1)), end: iso(monthEnd) });
    for (const yr of [...(options.years ?? [])].reverse()) out.push({ id: `y${yr}`, label: `Calendar ${yr}`, start: `${yr}-01-01`, end: `${yr}-12-31` });
    return out;
  }, [options]);
}

export function DateRangePicker() {
  const { filters, patchFilters, options } = useApp();
  const presets = useDatePresets();
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState({ start: filters.start_date ?? '', end: filters.end_date ?? '' });
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);
  useEffect(() => {
    const h = () => setOpen(true);
    window.addEventListener('meridian:open-dates', h);
    return () => window.removeEventListener('meridian:open-dates', h);
  }, []);
  useEffect(() => { setCustom({ start: filters.start_date ?? '', end: filters.end_date ?? '' }); }, [filters.start_date, filters.end_date]);
  const matches = presets.filter((p) => p.start === filters.start_date && p.end === filters.end_date);
  const active = matches.find((p) => /^y\d{4}$/.test(p.id)) ?? matches[0];
  const label = active?.label.replace(/^Calendar /, '') ?? `${fmtDate(filters.start_date)} – ${fmtDate(filters.end_date)}`;
  const cmpLabel: Record<Comparison, string> = { previous_period: 'vs previous period', previous_year: 'vs same period last year', none: 'no comparison' };
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="dialog" aria-expanded={open}
        className="inline-flex h-8 items-center gap-2 rounded-md border border-line-strong bg-panel px-2.5 text-sm hover:bg-panel-2">
        <CalendarRange size={15} className="text-ink-2" />
        <span className="font-medium">{label}</span>
        <span className="hidden text-xs text-ink-3 md:inline">{cmpLabel[filters.comparison]}</span>
        <ChevronDown size={14} className="opacity-60" />
      </button>
      {open && (
        <div role="dialog" aria-label="Date range" className="absolute left-0 top-10 z-40 w-[300px] rounded-lg border border-line bg-panel shadow-pop">
          <ul className="p-1">
            {presets.map((p) => {
              const on = p.id === active?.id;
              return (
                <li key={p.id}>
                  <button onClick={() => { patchFilters({ start_date: p.start, end_date: p.end }); setOpen(false); }}
                    className={cx('flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-panel-2', on && 'font-semibold')}>
                    {p.label}{on && <Check size={16} strokeWidth={2.6} className="text-accent" />}
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="border-t border-line p-3">
            <p className="mb-2 text-xs font-medium text-ink-2">Custom range</p>
            <div className="flex items-center gap-2">
              <input type="date" aria-label="Start date" value={custom.start} min={options?.date_min ?? undefined} max={options?.date_max ?? undefined}
                onChange={(e) => setCustom((c) => ({ ...c, start: e.target.value }))} className="h-8 w-full rounded-md border border-line-strong bg-panel px-2 text-xs" />
              <span className="text-ink-3">to</span>
              <input type="date" aria-label="End date" value={custom.end} min={options?.date_min ?? undefined} max={options?.date_max ?? undefined}
                onChange={(e) => setCustom((c) => ({ ...c, end: e.target.value }))} className="h-8 w-full rounded-md border border-line-strong bg-panel px-2 text-xs" />
            </div>
            <label className="mt-3 flex items-center justify-between gap-2 text-xs text-ink-2">
              Compare with
              <select value={filters.comparison} onChange={(e) => patchFilters({ comparison: e.target.value as Comparison })}
                className="h-7 rounded-md border border-line-strong bg-panel px-1.5 text-xs text-ink">
                <option value="previous_period">Previous period</option>
                <option value="previous_year">Same period last year</option>
                <option value="none">No comparison</option>
              </select>
            </label>
            <div className="mt-3 flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
              <Button size="sm" variant="primary" disabled={!custom.start || !custom.end || custom.start > custom.end}
                onClick={() => { patchFilters({ start_date: custom.start, end_date: custom.end }); setOpen(false); }}>Apply range</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ active filter chips */
export function ActiveChips() {
  const { filters, setDimension, dimLabel } = useApp();
  const dims = (Object.keys(filters) as (keyof Filters)[]).filter((k) => Array.isArray(filters[k]) && (filters[k] as string[]).length) as Dimension[];
  if (!dims.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Active filters">
      {dims.flatMap((d) => filters[d].map((v) => (
        <span key={`${d}-${v}`} className="inline-flex items-center gap-1 rounded-full border border-line-strong bg-panel py-0.5 pl-2.5 pr-1 text-xs">
          <span className="text-ink-3">{dimLabel(d)}:</span><span className="font-medium">{v}</span>
          <button aria-label={`Remove ${v}`} onClick={() => setDimension(d, filters[d].filter((x) => x !== v))}
            className="rounded-full p-0.5 text-ink-3 hover:bg-panel-2 hover:text-ink"><X size={12} /></button>
        </span>
      )))}
    </div>
  );
}
