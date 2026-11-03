import { useState } from 'react';
import { ChartCard } from '../components/charts/ChartCard';
import { BarList, GroupedColumns } from '../components/charts/charts';
import { DrillBreakdown } from '../components/charts/DrillBreakdown';
import { Heatmap } from '../components/charts/Heatmap';
import { isUsStates, TileMap, type MapMetric } from '../components/charts/TileMap';
import { DataTable } from '../components/data/DataTable';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { ErrorNote, NotSupported, Panel, Segmented, Stat } from '../components/ui/primitives';
import { fmtCurrency, fmtPercent } from '../lib/format';
import { navigate } from '../lib/hooks';
import type { BreakdownRow, Matrix, ScopeMeta } from '../lib/types';
import { useModule } from '../lib/useModule';
import { useApp } from '../state/AppState';

interface RegData {
  meta: ScopeMeta; available: boolean; reason?: string; requires?: string[]; levels: string[];
  region?: BreakdownRow[]; state?: BreakdownRow[]; city?: BreakdownRow[]; country?: BreakdownRow[];
  top_cities?: BreakdownRow[]; bottom_cities?: BreakdownRow[];
  penetration: { level: string; rows: Record<string, number | string | null>[]; active_states: number | null; known_states: number | null;
    active_cities: number | null; known_cities: number | null; revenue_per_active_city: number | null; note: string };
  heatmap: Matrix;
}

export default function Regional() {
  const { filters, toggleFilter, dimLabel } = useApp();
  const { data, loading, error, reload } = useModule<RegData>('regional');
  const [metric, setMetric] = useState<MapMetric>('revenue');
  const [cityView, setCityView] = useState<'top' | 'bottom'>('top');
  if (data && !data.available) {
    return (<div className="space-y-5"><PageHeader title="Regional analytics" />
      <NotSupported title="Regional analytics needs a location column" reason={data.reason ?? ''} requires={data.requires} onMap={() => navigate('data')} /></div>);
  }
  const showMap = !!data?.state?.length && isUsStates(data.state.map((s) => s.key));
  const top = data?.levels[0] ?? 'region';
  const growthRows = (data?.[top as 'region'] ?? []).map((r) => ({ key: r.key, current: r.revenue, previous: r.prev_revenue ?? null, growth: r.growth ?? null }));
  const cities = cityView === 'top' ? data?.top_cities ?? [] : data?.bottom_cities ?? [];
  const pen = data?.penetration;
  return (
    <div className="space-y-5">
      <PageHeader title="Regional analytics" meta={<ScopeNote meta={data?.meta} />}
        description="Geographic performance from region down to city, growth by market, and how much of the known footprint is active." />
      {error && <ErrorNote error={error} onRetry={reload} />}

      {pen && (
        <Panel loading={loading} bodyClass="px-5 py-5">
          <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
            {pen.active_states !== null && <Stat label="Active states" value={`${pen.active_states} of ${pen.known_states}`} hint="States with sales in this period" />}
            {pen.active_cities !== null && <Stat label="Active cities" value={`${pen.active_cities} of ${pen.known_cities}`} hint="Cities with sales in this period" />}
            <Stat label={`Largest ${dimLabel(top).toLowerCase()}`} value={data?.[top as 'region']?.[0]?.key ?? '—'} hint={`${fmtPercent(data?.[top as 'region']?.[0]?.share)} of revenue`} />
            {pen.revenue_per_active_city !== null && <Stat label="Revenue per active city" value={fmtCurrency(pen.revenue_per_active_city)} />}
          </div>
        </Panel>
      )}

      <div className="grid gap-5 xl:grid-cols-12">
        {showMap && (
          <ChartCard className="xl:col-span-7" title="Geographic performance" subtitle="Equal-size state tiles. Click a state to filter"
            controls={<Segmented value={metric} onChange={setMetric} label="Map metric" options={[{ value: 'revenue', label: 'Revenue' }, { value: 'margin', label: 'Margin' },
              { value: 'growth', label: 'Growth', disabled: !data?.meta.has_comparison }]} />}
            loading={loading} rows={data?.state ?? []} height={440}
            columns={[{ key: 'key', label: 'State', format: 'text' }, { key: 'region', label: 'Region', format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' },
              { key: 'share', label: 'Share', format: 'percent' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'growth', label: 'Growth', format: 'signed' }]}>
            <TileMap rows={data?.state ?? []} metric={metric} selected={filters.state} onSelect={(s) => toggleFilter('state', s)} />
          </ChartCard>
        )}
        <DrillBreakdown className={showMap ? 'xl:col-span-5' : 'xl:col-span-12'} title="Region-wise revenue" chain={['region', 'state', 'city']} limit={15} />
      </div>

      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-6" title={`${dimLabel(top)} growth comparison`} subtitle={data?.meta.has_comparison ? `${data.meta.label} against ${data.meta.comparison_label}. Click to filter` : 'Select a period with a comparison to see growth'}
          loading={loading} rows={growthRows} height={280}
          columns={[{ key: 'key', label: dimLabel(top), format: 'text' }, { key: 'current', label: 'Current', format: 'currency' }, { key: 'previous', label: 'Previous', format: 'currency' }, { key: 'growth', label: 'Growth', format: 'signed' }]}>
          <GroupedColumns rows={growthRows} currentLabel={data?.meta.label ?? 'Current'} previousLabel={data?.meta.has_comparison ? data.meta.comparison_label : undefined}
            selected={filters[top as 'region']} onSelect={(k) => toggleFilter(top as 'region', k)} />
        </ChartCard>
        {data?.city && (
          <ChartCard className="xl:col-span-6" title="City-wise sales" subtitle="Click a city to filter" loading={loading} rows={cities} height={Math.max(180, cities.length * 30 + 16)}
            controls={<Segmented value={cityView} onChange={setCityView} label="Cities" options={[{ value: 'top', label: 'Top 15' }, { value: 'bottom', label: 'Bottom 5' }]} />}
            columns={[{ key: 'key', label: 'City', format: 'text' }, { key: 'state', label: 'State', format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }]}>
            <BarList rows={cities} selected={filters.city} onSelect={(k) => toggleFilter('city', k)} secondary={{ key: 'margin', label: 'Margin', format: 'percent' }} />
          </ChartCard>
        )}
      </div>

      {data && data.heatmap.rows.length > 0 && (
        <ChartCard title={`${dimLabel(top)} by month`} subtitle="Revenue pattern over time. Darker cells are larger. Click a row to filter" loading={loading}
          rows={data.heatmap.cells as unknown as Record<string, unknown>[]} height={Math.max(150, data.heatmap.rows.length * 32 + 60)}
          columns={[{ key: 'row', label: dimLabel(top), format: 'text' }, { key: 'col', label: 'Month', format: 'text' }, { key: 'value', label: 'Revenue', format: 'currency' }]}>
          <Heatmap matrix={data.heatmap} onSelectRow={(r) => toggleFilter(top as 'region', r)} />
        </ChartCard>
      )}

      {pen && (
        <Panel title="Market penetration" subtitle={pen.note} loading={loading}>
          <DataTable rows={pen.rows} initialSort={{ key: 'share', dir: 'desc' }}
            columns={[{ key: 'key', label: dimLabel(pen.level), format: 'text' }, { key: 'share', label: 'Revenue share', format: 'percent' },
              ...(pen.active_states !== null ? [{ key: 'active_states', label: 'Active states', format: 'number' as const }, { key: 'state_coverage', label: 'State coverage', format: 'percent' as const }] : []),
              ...(pen.active_cities !== null ? [{ key: 'active_cities', label: 'Active cities', format: 'number' as const }, { key: 'city_coverage', label: 'City coverage', format: 'percent' as const },
                { key: 'revenue_per_city', label: 'Revenue per active city', format: 'currency' as const }] : [])]} />
        </Panel>
      )}
    </div>
  );
}
