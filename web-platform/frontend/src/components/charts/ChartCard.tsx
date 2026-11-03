import { CalendarRange, ChevronRight, Download, Image as ImageIcon, Table2, ChartColumn, FileSpreadsheet } from 'lucide-react';
import { useRef, useState, type ReactNode } from 'react';
import { exportChartPng, exportRowsCsv } from '../../lib/exporting';
import { useClickOutside } from '../../lib/hooks';
import { useApp } from '../../state/AppState';
import { DataTable, type Column } from '../data/DataTable';
import { cx, EmptyState, IconButton } from '../ui/primitives';

export interface Crumb { label: string; onClick?: () => void }

/**
 * Every chart sits in a ChartCard: title, drill breadcrumb, chart/table toggle
 * (table view is the accessible fallback), PNG + CSV export and the active period.
 */
export function ChartCard<T extends Record<string, unknown>>({
  title, subtitle, controls, children, rows, columns, height = 300, crumbs, loading, empty, footnote, className, period = true,
}: {
  title: string; subtitle?: ReactNode; controls?: ReactNode; children: ReactNode; rows: T[]; columns: Column<T>[];
  height?: number; crumbs?: Crumb[]; loading?: boolean; empty?: string | false; footnote?: ReactNode; className?: string; period?: boolean;
}) {
  const { chart, filters } = useApp();
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const [menu, setMenu] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  useClickOutside(menuRef, () => setMenu(false), menu);
  const isEmpty = empty !== false && rows.length === 0 && !loading;

  const periodText = filters.start_date || filters.end_date
    ? `${filters.start_date ?? 'start'} to ${filters.end_date ?? 'latest'}` : 'All dates';

  return (
    <section className={cx('flex min-w-0 flex-col rounded-xl border border-line bg-panel', loading && 'loading-bar', className)}>
      <header className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 px-5 pt-4">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold leading-snug">{title}</h2>
          {crumbs && crumbs.length > 1 ? (
            <nav aria-label="Drill path" className="mt-0.5 flex flex-wrap items-center gap-0.5 text-xs">
              {crumbs.map((c, i) => (
                <span key={i} className="inline-flex items-center gap-0.5">
                  {i > 0 && <ChevronRight size={12} className="text-ink-3" />}
                  {c.onClick && i < crumbs.length - 1
                    ? <button onClick={c.onClick} className="text-accent-ink hover:underline">{c.label}</button>
                    : <span className="text-ink-2">{c.label}</span>}
                </span>
              ))}
            </nav>
          ) : subtitle ? <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p> : null}
        </div>
        <div className="flex items-center gap-1">
          {controls}
          <IconButton label={view === 'chart' ? 'Show as table' : 'Show as chart'} onClick={() => setView(view === 'chart' ? 'table' : 'chart')}>
            {view === 'chart' ? <Table2 size={16} /> : <ChartColumn size={16} />}
          </IconButton>
          <div className="relative" ref={menuRef}>
            <IconButton label="Export chart" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}><Download size={16} /></IconButton>
            {menu && (
              <div role="menu" className="absolute right-0 top-9 z-30 w-44 rounded-lg border border-line bg-panel p-1 shadow-pop">
                <button role="menuitem" disabled={view !== 'chart'} className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm hover:bg-panel-2 disabled:opacity-40"
                  onClick={() => { setMenu(false); if (bodyRef.current) void exportChartPng(bodyRef.current, title, chart.surface, periodText, chart.ink, chart.tick); }}>
                  <ImageIcon size={15} /> Chart as PNG
                </button>
                <button role="menuitem" className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm hover:bg-panel-2"
                  onClick={() => { setMenu(false); exportRowsCsv(rows, columns.map((c) => ({ key: c.key, label: c.label })), title); }}>
                  <FileSpreadsheet size={15} /> Data as CSV
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <div ref={bodyRef} className="relative flex-1 px-5 pb-3 pt-3">
        {isEmpty ? (
          <div style={{ minHeight: height }} className="flex items-center justify-center">
            <EmptyState title="No data for these filters">{typeof empty === 'string' ? empty : 'Widen the date range or clear a filter.'}</EmptyState>
          </div>
        ) : view === 'chart' ? (
          <div style={{ height }} className="w-full">{children}</div>
        ) : (
          <DataTable rows={rows} columns={columns} maxHeight={height + 40} dense />
        )}
      </div>
      {(period || footnote) && (
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-5 py-2 text-2xs text-ink-3">
          {period ? (
            <button onClick={() => window.dispatchEvent(new CustomEvent('meridian:open-dates'))}
              className="inline-flex items-center gap-1 hover:text-ink-2" title="Change the date range">
              <CalendarRange size={12} /> {periodText}
            </button>
          ) : <span />}
          {footnote && <span className="text-right">{footnote}</span>}
        </footer>
      )}
    </section>
  );
}
