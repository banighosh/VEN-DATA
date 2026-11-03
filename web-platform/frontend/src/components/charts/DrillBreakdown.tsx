import { useModule } from '../../lib/useModule';
import type { BreakdownRow, Dimension, ValueFormat } from '../../lib/types';
import { drillLevel, useApp } from '../../state/AppState';
import { ChartCard, type Crumb } from './ChartCard';
import { BarList } from './charts';

const plural = (s: string) => (s.endsWith('y') ? `${s.slice(0, -1)}ies` : s.endsWith('s') ? s : `${s}s`).toLowerCase();

/**
 * Ranked bars that drill down a hierarchy (e.g. region → state → city).
 * Clicking a bar applies it as a global filter, so every other chart cross-filters,
 * and this chart steps down one level. The breadcrumb steps back up.
 */
export function DrillBreakdown({ title, chain, metric = 'revenue', format = 'currency', limit = 12, className }: {
  title: string; chain: Dimension[]; metric?: string; format?: ValueFormat; limit?: number; className?: string;
}) {
  const { filters, setFilters, toggleFilter, caps, colorFor, dimLabel, options } = useApp();
  const avail = (d: Dimension) => !!caps?.filters[d]?.available;
  const usable = chain.filter(avail);
  const level = usable.length ? drillLevel(filters, usable, avail) : chain[0];
  const { data, loading } = useModule<{ rows: BreakdownRow[]; label: string }>('breakdown', { dimension: level, sort_by: metric, limit }, usable.length > 0);
  if (!usable.length) return null;
  const idx = usable.indexOf(level);
  const child = usable[idx + 1];
  const crumbs: Crumb[] = [{
    label: `All ${plural(dimLabel(usable[0]))}`,
    onClick: () => setFilters((f) => { const n = { ...f }; usable.forEach((d) => { n[d] = []; }); return n; }),
  }];
  usable.slice(0, idx).forEach((d, i) => {
    const v = filters[d][0];
    crumbs.push({ label: v, onClick: () => setFilters((f) => { const n = { ...f }; usable.slice(i + 1).forEach((x) => { n[x] = []; }); return n; }) });
  });
  if (idx > 0) crumbs.push({ label: `${dimLabel(level)} breakdown` });
  const rows = data?.rows.filter((r) => r.revenue > 0 || metric !== 'revenue') ?? [];
  const small = (options?.dimensions[level]?.values.length ?? 99) <= 8;
  return (
    <ChartCard title={title} subtitle={`By ${dimLabel(level).toLowerCase()}. ${child ? 'Click a bar to drill down' : 'Click a bar to filter'}`}
      crumbs={crumbs} loading={loading} rows={rows} className={className}
      height={Math.max(160, Math.min(rows.length, limit) * 30 + 16)}
      columns={[{ key: 'key', label: dimLabel(level), format: 'text' }, { key: metric, label: metric === 'revenue' ? 'Revenue' : metric, format },
        { key: 'share', label: 'Share', format: 'percent' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'growth', label: 'Growth', format: 'percent' }]}>
      <BarList rows={rows} valueKey={metric} format={format} selected={filters[level]}
        colorFor={small ? (k) => colorFor(level, k) : undefined}
        secondary={{ key: 'margin', label: 'Margin', format: 'percent' }}
        onSelect={(k) => (child ? setFilters((f) => ({ ...f, [level]: [k] })) : toggleFilter(level, k))} />
    </ChartCard>
  );
}
