import {
  Activity, BadgeDollarSign, Bell, Bookmark, BrainCircuit, ChevronDown, Cog, Database, FileDown, FileSpreadsheet, Gauge,
  LayoutDashboard, Map as MapIcon, Menu, Moon, Package, Printer, RotateCcw, Search, SlidersHorizontal, Sun, Table2, TrendingUp,
  Truck, User, Users, X, OctagonAlert, TriangleAlert, Laptop, Trash,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, compactFilters, downloadPost, openHtmlReport, type Preset } from '../../lib/api';
import { fmtCurrency, fmtChange } from '../../lib/format';
import { navigate, useAsync, useClickOutside, useDebounced, type Page } from '../../lib/hooks';
import type { DatasetDetail, Dimension, Kpi } from '../../lib/types';
import { useApp } from '../../state/AppState';
import { Button, cx, IconButton } from '../ui/primitives';
import { ActiveChips, DateRangePicker, MultiSelect } from './FilterControls';

export const NAV: { group: string; items: { page: Page; label: string; icon: typeof LayoutDashboard }[] }[] = [
  { group: 'Overview', items: [
    { page: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { page: 'executive', label: 'Executive Overview', icon: Gauge },
  ] },
  { group: 'Analytics', items: [
    { page: 'performance', label: 'Performance', icon: TrendingUp },
    { page: 'financial', label: 'Financial Analytics', icon: BadgeDollarSign },
    { page: 'customers', label: 'Customer Analytics', icon: Users },
    { page: 'products', label: 'Product Analytics', icon: Package },
    { page: 'regional', label: 'Regional Analytics', icon: MapIcon },
    { page: 'operations', label: 'Operational Analytics', icon: Truck },
    { page: 'insights', label: 'AI Insights', icon: BrainCircuit },
  ] },
  { group: 'Data', items: [
    { page: 'explorer', label: 'Data Explorer', icon: Table2 },
    { page: 'data', label: 'Data Management', icon: Database },
  ] },
];

export function Sidebar({ page, open, onClose }: { page: Page; open: boolean; onClose: () => void }) {
  const link = (p: Page, label: string, Icon: typeof LayoutDashboard) => (
    <a key={p} href={`#/${p}`} onClick={onClose} aria-current={page === p ? 'page' : undefined}
      className={cx('flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13.5px] transition-colors',
        page === p ? 'bg-sidebar-active font-medium text-white' : 'text-sidebar-ink hover:bg-white/5 hover:text-white')}>
      <Icon size={17} strokeWidth={1.9} className={page === p ? 'text-[#7fb2f0]' : 'opacity-80'} />{label}
    </a>
  );
  return (
    <>
      {open && <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={onClose} />}
      <aside className={cx('fixed inset-y-0 left-0 z-50 flex w-[244px] flex-col bg-sidebar transition-transform lg:static lg:translate-x-0',
        open ? 'translate-x-0' : '-translate-x-full')}>
        <div className="flex h-14 items-center gap-2.5 px-5">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#173a66" /><path d="M8 23V13M14 23V9M20 23v-6M26 23V11" stroke="#7FB2F0" strokeWidth="3" strokeLinecap="round" /></svg>
          <span className="text-[15px] font-semibold tracking-tight text-white">Meridian BI</span>
          <IconButton label="Close menu" onClick={onClose} className="ml-auto text-sidebar-ink hover:bg-white/10 lg:hidden"><X size={18} /></IconButton>
        </div>
        <nav className="scroll-thin flex-1 overflow-y-auto px-3 pb-4" aria-label="Main">
          {NAV.map((g) => (
            <div key={g.group} className="mt-4">
              <p className="px-2.5 pb-1.5 text-2xs font-medium text-sidebar-muted">{g.group}</p>
              <div className="space-y-0.5">{g.items.map((i) => link(i.page, i.label, i.icon))}</div>
            </div>
          ))}
        </nav>
        <div className="border-t border-white/10 px-3 py-3">{link('settings', 'Settings', Cog)}</div>
      </aside>
    </>
  );
}

/* ------------------------------------------------------------------ top navigation */
function WorkspaceSelector() {
  const { datasets, dataset, setDatasetId } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);
  const ready = datasets.filter((d) => d.status === 'ready');
  return (
    <div className="relative min-w-0" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open}
        className="flex h-9 w-full max-w-[260px] items-center gap-2 rounded-md px-2 text-left hover:bg-panel-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-navy text-white dark:bg-sidebar-active"><Database size={15} /></span>
        <span className="min-w-0">
          <span className="block text-2xs leading-tight text-ink-3">Workspace dataset</span>
          <span className="block truncate text-sm font-semibold leading-tight">{dataset?.name ?? 'No dataset yet'}</span>
        </span>
        <ChevronDown size={14} className="shrink-0 text-ink-3" />
      </button>
      {open && (
        <div className="absolute left-0 top-11 z-40 w-80 max-w-[calc(100vw-2rem)] rounded-lg border border-line bg-panel p-1 shadow-pop">
          {ready.map((d) => (
            <button key={d.id} onClick={() => { setDatasetId(d.id); setOpen(false); }}
              className={cx('flex w-full flex-col rounded-md px-3 py-2 text-left hover:bg-panel-2', d.id === dataset?.id && 'bg-accent-soft')}>
              <span className="text-sm font-medium">{d.name}</span>
              <span className="text-xs text-ink-3">{d.valid_row_count.toLocaleString()} rows, {d.date_min?.slice(0, 7)} to {d.date_max?.slice(0, 7)}</span>
            </button>
          ))}
          <div className="mt-1 border-t border-line pt-1">
            <button onClick={() => { setOpen(false); navigate('data'); }} className="w-full rounded-md px-3 py-2 text-left text-sm text-accent-ink hover:bg-panel-2">Upload a new dataset</button>
          </div>
        </div>
      )}
    </div>
  );
}

function GlobalSearch() {
  const { dataset, setDimension, toast, dimLabel } = useApp();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useClickOutside(ref, () => setOpen(false), open);
  const dq = useDebounced(q.trim(), 180);
  const { data: hits } = useAsync((s) => api.search(dataset!.id, dq, s), [dataset?.id, dq], !!dataset && dq.length >= 1);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === '/' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement)) {
        e.preventDefault(); input.current?.focus();
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);
  const pages = useMemo(() => NAV.flatMap((g) => g.items).filter((i) => dq && i.label.toLowerCase().includes(dq.toLowerCase())), [dq]);
  const items: { kind: 'page' | 'value'; label: string; hint: string; run: () => void }[] = [
    ...pages.map((p) => ({ kind: 'page' as const, label: p.label, hint: 'Go to page', run: () => navigate(p.page) })),
    ...((dq && hits) || []).slice(0, 8).map((h) => ({
      kind: 'value' as const, label: h.value, hint: `${dimLabel(h.dimension)}, ${fmtCurrency(h.revenue)} revenue`,
      run: () => { setDimension(h.dimension as Dimension, [h.value]); toast(`Filtered to ${dimLabel(h.dimension)}: ${h.value}`, 'success'); },
    })),
  ];
  const choose = (i: number) => { items[i]?.run(); setQ(''); setOpen(false); input.current?.blur(); };
  return (
    <div className="relative w-full max-w-[380px]" ref={ref}>
      <div className="flex h-9 items-center gap-2 rounded-md border border-line bg-panel-2 px-2.5 focus-within:border-accent">
        <Search size={15} className="text-ink-3" />
        <input ref={input} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); setIdx(0); }} onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, items.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            else if (e.key === 'Enter') { e.preventDefault(); choose(idx); }
            else if (e.key === 'Escape') setOpen(false);
          }}
          placeholder="Search products, places, accounts or pages" aria-label="Global search"
          className="w-full bg-transparent text-sm outline-none placeholder:text-ink-3" />
        <kbd className="hidden rounded border border-line px-1.5 text-2xs text-ink-3 sm:block">/</kbd>
      </div>
      {open && dq && (
        <div className="absolute left-0 right-0 top-11 z-40 rounded-lg border border-line bg-panel p-1 shadow-pop" role="listbox">
          {items.length === 0 && <p className="px-3 py-3 text-sm text-ink-3">No matches for “{dq}”.</p>}
          {items.map((it, i) => (
            <button key={`${it.kind}-${it.label}-${i}`} role="option" aria-selected={i === idx} onMouseEnter={() => setIdx(i)} onClick={() => choose(i)}
              className={cx('flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left', i === idx && 'bg-panel-2')}>
              <span className="truncate text-sm font-medium">{it.label}</span>
              <span className="shrink-0 text-xs text-ink-3">{it.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Notifications() {
  const { dataset, filters } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);
  const { data: detail } = useAsync((s) => api.dataset(dataset!.id).then((d) => { void s; return d; }), [dataset?.id, dataset?.updated_at], !!dataset);
  const { data: k } = useAsync((s) => api.analytics<{ kpis: Kpi[]; attention: string[]; meta: { comparison_label: string } }>(dataset!.id, 'kpis', filters, {}, s),
    [dataset?.id, JSON.stringify(compactFilters(filters))], !!dataset);
  const quality = (detail as DatasetDetail | undefined)?.quality?.issues.filter((i) => i.severity !== 'info') ?? [];
  const attention = k ? k.kpis.filter((c) => k.attention.includes(c.key)) : [];
  const count = quality.filter((q) => q.severity === 'critical').length + attention.length;
  return (
    <div className="relative" ref={ref}>
      <IconButton label={`Notifications${count ? ` (${count})` : ''}`} onClick={() => setOpen((o) => !o)} className="relative h-9 w-9">
        <Bell size={18} />
        {count > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-bad px-1 text-[10px] font-semibold text-white">{count}</span>}
      </IconButton>
      {open && (
        <div className="absolute right-0 top-11 z-40 w-[360px] max-w-[calc(100vw-1.5rem)] rounded-lg border border-line bg-panel shadow-pop">
          <p className="border-b border-line px-4 py-2.5 text-sm font-semibold">Notifications</p>
          <div className="scroll-thin max-h-[420px] overflow-y-auto p-2">
            {attention.map((c) => (
              <button key={c.key} onClick={() => { setOpen(false); navigate('executive'); }} className="flex w-full gap-2.5 rounded-md px-2 py-2 text-left hover:bg-panel-2">
                <TriangleAlert size={16} className="mt-0.5 shrink-0 text-warn" />
                <span className="text-sm"><b className="font-medium">{c.label}</b> moved {fmtChange(c.change, c.change_type)} vs {k?.meta.comparison_label}. Needs attention.</span>
              </button>
            ))}
            {quality.map((q, i) => (
              <button key={i} onClick={() => { setOpen(false); navigate('data'); }} className="flex w-full gap-2.5 rounded-md px-2 py-2 text-left hover:bg-panel-2">
                {q.severity === 'critical' ? <OctagonAlert size={16} className="mt-0.5 shrink-0 text-bad" /> : <TriangleAlert size={16} className="mt-0.5 shrink-0 text-warn" />}
                <span className="line-clamp-3 text-sm text-ink-2"><b className="font-medium text-ink">Data quality.</b> {q.message}</span>
              </button>
            ))}
            {!attention.length && !quality.length && <p className="px-2 py-6 text-center text-sm text-ink-3">Nothing needs your attention.</p>}
          </div>
        </div>
      )}
    </div>
  );
}

function ProfileMenu() {
  const { prefs, setPrefs } = useApp();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);
  const opts = [{ v: 'light', l: 'Light', i: Sun }, { v: 'dark', l: 'Dark', i: Moon }, { v: 'system', l: 'System', i: Laptop }] as const;
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-label="User profile" aria-expanded={open}
        className="flex h-9 items-center gap-2 rounded-md pl-1 pr-2 hover:bg-panel-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-navy text-white dark:bg-sidebar-active"><User size={15} /></span>
        <span className="hidden text-sm font-medium xl:inline">Analyst</span>
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-40 w-64 rounded-lg border border-line bg-panel p-2 shadow-pop">
          <div className="px-2 py-1.5">
            <p className="text-sm font-semibold">Analyst</p>
            <p className="text-xs text-ink-3">Local workspace. Sign-in is not configured.</p>
          </div>
          <p className="mt-2 px-2 text-xs text-ink-2">Theme</p>
          <div className="mt-1 grid grid-cols-3 gap-1 px-1">
            {opts.map(({ v, l, i: Icon }) => (
              <button key={v} onClick={() => setPrefs({ themePref: v })} aria-pressed={prefs.themePref === v}
                className={cx('flex flex-col items-center gap-1 rounded-md border py-2 text-xs', prefs.themePref === v ? 'border-accent bg-accent-soft text-accent-ink' : 'border-line hover:bg-panel-2')}>
                <Icon size={15} />{l}
              </button>
            ))}
          </div>
          <button onClick={() => { setOpen(false); navigate('settings'); }} className="mt-2 flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-panel-2"><Cog size={15} /> Settings</button>
        </div>
      )}
    </div>
  );
}

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { theme, setPrefs } = useApp();
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-line bg-panel px-3 sm:gap-3 sm:px-4 lg:px-6">
      <IconButton label="Open menu" onClick={onMenu} className="lg:hidden"><Menu size={20} /></IconButton>
      <WorkspaceSelector />
      <div className="mx-auto hidden flex-1 justify-center md:flex"><GlobalSearch /></div>
      <div className="ml-auto flex shrink-0 items-center gap-1 md:ml-0">
        <div className="hidden sm:block"><DateRangePicker /></div>
        <IconButton label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={() => setPrefs({ themePref: theme === 'dark' ? 'light' : 'dark' })} className="hidden h-9 w-9 sm:inline-flex">
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </IconButton>
        <Notifications />
        <ProfileMenu />
      </div>
    </header>
  );
}

/* ------------------------------------------------------------------ global filter bar */
const PRIMARY: Dimension[] = ['region', 'category', 'customer_segment', 'business_unit', 'channel'];
const SECONDARY: Dimension[] = ['state', 'city', 'subcategory', 'product', 'customer'];

function SavedViews() {
  const { dataset, filters, setFilters, toast } = useApp();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);
  const { data: presets, reload } = useAsync(() => api.presets(dataset?.id), [dataset?.id, open], open);
  const save = async () => {
    if (!name.trim()) return;
    try {
      await api.savePreset({ name: name.trim(), dataset_id: dataset?.id ?? null, filters: compactFilters(filters) });
      toast(`Saved view “${name.trim()}”`, 'success'); setName(''); reload();
    } catch (e) { toast((e as Error).message, 'error'); }
  };
  const apply = (p: Preset) => { setFilters({ ...filters, ...emptyDims(), ...p.filters } as typeof filters); setOpen(false); toast(`Applied view “${p.name}”`, 'success'); };
  return (
    <div className="relative" ref={ref}>
      <Button size="sm" variant="ghost" icon={<Bookmark size={14} />} onClick={() => setOpen((o) => !o)} aria-expanded={open}>Saved views</Button>
      {open && (
        <div className="absolute right-0 top-9 z-40 w-72 rounded-lg border border-line bg-panel shadow-pop">
          <div className="p-3">
            <p className="text-xs font-medium text-ink-2">Save the current filters</p>
            <div className="mt-2 flex gap-2">
              <input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && save()} placeholder="View name, e.g. West online 2021"
                className="h-8 w-full rounded-md border border-line-strong bg-panel px-2 text-sm" aria-label="View name" />
              <Button size="sm" variant="primary" onClick={save} disabled={!name.trim()}>Save</Button>
            </div>
          </div>
          <ul className="scroll-thin max-h-60 overflow-y-auto border-t border-line p-1">
            {(presets ?? []).length === 0 && <li className="px-3 py-3 text-xs text-ink-3">No saved views yet.</li>}
            {(presets ?? []).map((p) => (
              <li key={p.id} className="group flex items-center rounded-md hover:bg-panel-2">
                <button onClick={() => apply(p)} className="min-w-0 flex-1 px-3 py-2 text-left">
                  <span className="block truncate text-sm font-medium">{p.name}</span>
                  <span className="block truncate text-2xs text-ink-3">{describeFilters(p.filters)}</span>
                </button>
                <IconButton label={`Delete ${p.name}`} onClick={async () => { await api.deletePreset(p.id); reload(); }} className="mr-1 opacity-0 group-hover:opacity-100 focus:opacity-100"><Trash size={14} /></IconButton>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

const emptyDims = () => ({ region: [], state: [], city: [], category: [], subcategory: [], product: [], customer_segment: [], business_unit: [], channel: [], customer: [] });

function describeFilters(f: Record<string, unknown>): string {
  const parts: string[] = [];
  if (f.start_date || f.end_date) parts.push(`${f.start_date ?? '…'} to ${f.end_date ?? '…'}`);
  for (const [k, v] of Object.entries(f)) if (Array.isArray(v) && v.length) parts.push(`${k.replace('_', ' ')}: ${v.join(', ')}`);
  return parts.join('; ') || 'All data';
}

function ExportMenu() {
  const { dataset, filters, toast } = useApp();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);
  const run = useCallback(async (fn: () => Promise<void>, done: string) => {
    setBusy(true); setOpen(false);
    try { await fn(); toast(done, 'success'); } catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(false); }
  }, [toast]);
  if (!dataset) return null;
  const body = { filters: compactFilters(filters) };
  const item = (icon: ReactNode, label: string, onClick: () => void) => (
    <button role="menuitem" onClick={onClick} className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm hover:bg-panel-2">{icon}{label}</button>
  );
  return (
    <div className="relative" ref={ref}>
      <Button size="sm" variant="ghost" icon={<FileDown size={14} />} onClick={() => setOpen((o) => !o)} loading={busy} aria-expanded={open}>Export</Button>
      {open && (
        <div role="menu" className="absolute right-0 top-9 z-40 w-64 rounded-lg border border-line bg-panel p-1 shadow-pop">
          {item(<FileSpreadsheet size={15} />, 'Dashboard report (Excel)', () => run(() => downloadPost(`/api/datasets/${dataset.id}/report`, { ...body, format: 'xlsx' }, 'report.xlsx'), 'Report downloaded'))}
          {item(<Printer size={15} />, 'Printable report (HTML / PDF)', () => run(() => openHtmlReport(`/api/datasets/${dataset.id}/report`, { ...body, format: 'html' }), 'Report opened in a new tab'))}
          <div className="my-1 border-t border-line" />
          {item(<FileDown size={15} />, 'Filtered data (CSV)', () => run(() => downloadPost(`/api/datasets/${dataset.id}/export`, { ...body, format: 'csv' }, 'data.csv'), 'Export downloaded'))}
          {item(<FileSpreadsheet size={15} />, 'Filtered data (Excel)', () => run(() => downloadPost(`/api/datasets/${dataset.id}/export`, { ...body, format: 'xlsx' }, 'data.xlsx'), 'Export downloaded'))}
        </div>
      )}
    </div>
  );
}

export function FilterBar() {
  const { resetFilters, activeFilterCount, filters, defaultFilters, caps } = useApp();
  const [more, setMore] = useState(false);
  const hasSecondaryActive = SECONDARY.some((d) => filters[d].length);
  const changed = activeFilterCount > 0 || filters.start_date !== defaultFilters.start_date || filters.end_date !== defaultFilters.end_date || filters.comparison !== defaultFilters.comparison;
  const secondaryAvailable = SECONDARY.filter((d) => caps?.filters[d]?.available);
  return (
    <div className="border-b border-line bg-panel/70 px-4 py-2.5 backdrop-blur lg:px-6">
      <div className="flex flex-wrap items-center gap-2">
        <div className="sm:hidden"><DateRangePicker /></div>
        <SlidersHorizontal size={15} className="hidden text-ink-3 sm:block" aria-hidden="true" />
        {PRIMARY.map((d) => <MultiSelect key={d} dim={d} />)}
        {secondaryAvailable.length > 0 && (
          <Button size="sm" variant="ghost" onClick={() => setMore((m) => !m)} aria-expanded={more || hasSecondaryActive}>
            {more || hasSecondaryActive ? 'Fewer filters' : 'More filters'}
          </Button>
        )}
        {changed && <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={resetFilters}>Reset</Button>}
        <div className="ml-auto flex items-center gap-1"><SavedViews /><ExportMenu /></div>
      </div>
      {(more || hasSecondaryActive) && <div className="mt-2 flex flex-wrap items-center gap-2 pl-0 sm:pl-6">{SECONDARY.map((d) => <MultiSelect key={d} dim={d} />)}</div>}
      {activeFilterCount > 0 && <div className="mt-2 pl-0 sm:pl-6"><ActiveChips /></div>}
    </div>
  );
}

export function PageHeader({ title, description, actions, meta }: { title: string; description?: ReactNode; actions?: ReactNode; meta?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-navy-ink">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-2">{description}</p>}
        {meta && <div className="mt-2">{meta}</div>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function ScopeNote({ meta }: { meta?: { label: string; comparison_label: string; has_comparison: boolean; rows: number; notes: string[] } }) {
  if (!meta) return null;
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
      <span className="inline-flex items-center gap-1"><Activity size={13} /> {meta.label}{meta.has_comparison ? ` compared with ${meta.comparison_label}` : ''}</span>
      <span>{meta.rows.toLocaleString()} transactions in scope</span>
      {meta.notes.map((n) => <span key={n} className="text-warn">{n}</span>)}
    </p>
  );
}
