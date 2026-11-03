import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { ChartCard } from '../components/charts/ChartCard';
import { DonutChart, TrendChart } from '../components/charts/charts';
import { DrillBreakdown } from '../components/charts/DrillBreakdown';
import { isUsStates, TileMap, type MapMetric } from '../components/charts/TileMap';
import { DataTable } from '../components/data/DataTable';
import { InsightList } from '../components/insights/InsightCard';
import { KpiStrip } from '../components/kpi/KpiStrip';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { Badge, Button, ErrorNote, Panel, Segmented } from '../components/ui/primitives';
import { navigate } from '../lib/hooks';
import type { BreakdownRow, Insight, Kpi, ScopeMeta } from '../lib/types';
import { useModule } from '../lib/useModule';
import { useApp } from '../state/AppState';

export interface Overview {
  meta: ScopeMeta; kpis: Kpi[]; attention: string[]; granularity: string;
  trend: { overlay: { label: string; current: number | null; previous: number | null; previous_label: string | null }[] };
  categories: BreakdownRow[]; regions: BreakdownRow[]; states: BreakdownRow[]; channels: BreakdownRow[]; products: BreakdownRow[];
  segments: BreakdownRow[]; insights: Insight[]; quality: { score: number; grade: string; critical: number; warnings: number };
}

export default function Dashboard() {
  const { dataset, filters, toggleFilter, colorFor, caps, dimLabel } = useApp();
  const { data, loading, error, reload } = useModule<Overview>('overview');
  const [mapMetric, setMapMetric] = useState<MapMetric>('revenue');
  const headline = data?.kpis.filter((k) => ['total_revenue', 'total_profit', 'profit_margin', 'growth_rate'].includes(k.key));
  const catDim = caps?.filters.category?.available ? 'category' : caps?.filters.channel?.available ? 'channel' : null;
  const catRows = catDim === 'category' ? data?.categories : data?.channels;
  const showMap = !!data?.states.length && isUsStates(data.states.map((s) => s.key));
  return (
    <div className="space-y-5">
      <PageHeader title="Dashboard" meta={<ScopeNote meta={data?.meta} />}
        description={`${dataset?.name}: headline performance, where it comes from, and what needs attention.`} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      <KpiStrip kpis={headline} comparisonLabel={data?.meta.comparison_label} attention={data?.attention} loading={loading && !!data} />

      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-8" title="Revenue trend" subtitle={`${data?.meta.label ?? ''} against the comparison period`}
          loading={loading} rows={data?.trend.overlay ?? []} height={290}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'current', label: data?.meta.label ?? 'Current', format: 'currency' },
            { key: 'previous', label: data?.meta.comparison_label || 'Previous', format: 'currency' }]}>
          <TrendChart data={data?.trend.overlay ?? []} currentLabel={data?.meta.label ?? 'Current'} previousLabel={data?.meta.has_comparison ? data.meta.comparison_label : undefined} />
        </ChartCard>
        {catDim && (
          <ChartCard className="xl:col-span-4" title={`Revenue by ${dimLabel(catDim).toLowerCase()}`} subtitle="Click a segment to filter"
            loading={loading} rows={catRows ?? []} height={290}
            columns={[{ key: 'key', label: dimLabel(catDim), format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'share', label: 'Share', format: 'percent' }]}>
            <DonutChart rows={catRows ?? []} colorFor={(k) => colorFor(catDim, k)} selected={filters[catDim]} onSelect={(k) => toggleFilter(catDim, k)} />
          </ChartCard>
        )}
      </div>

      <div className="grid gap-5 xl:grid-cols-12">
        {showMap && (
          <ChartCard className="xl:col-span-7" title="Sales by state" subtitle="Click a state to filter every view"
            controls={<Segmented value={mapMetric} onChange={setMapMetric} label="Map metric"
              options={[{ value: 'revenue', label: 'Revenue' }, { value: 'margin', label: 'Margin' }, { value: 'growth', label: 'Growth', disabled: !data?.meta.has_comparison }]} />}
            loading={loading} rows={data?.states ?? []} height={430}
            columns={[{ key: 'key', label: 'State', format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' },
              { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'growth', label: 'Growth', format: 'percent' }]}>
            <TileMap rows={data?.states ?? []} metric={mapMetric} selected={filters.state} onSelect={(s) => toggleFilter('state', s)} />
          </ChartCard>
        )}
        <DrillBreakdown className={showMap ? 'xl:col-span-5' : 'xl:col-span-12'} title="Where revenue comes from" chain={['region', 'state', 'city']} />
      </div>

      <div className="grid items-start gap-5 xl:grid-cols-12">
        <Panel className="xl:col-span-8" title="Top insights" subtitle="Measured observations on the left; interpretation on the right"
          actions={<Button size="sm" variant="ghost" onClick={() => navigate('insights')}>All insights</Button>}>
          <InsightList insights={data?.insights.slice(0, 3)} compact />
        </Panel>
        <Panel className="xl:col-span-4" title="Data quality" subtitle={dataset?.source_filename}
          actions={<Button size="sm" variant="ghost" onClick={() => navigate('data')}>Report</Button>}>
          {data && (
            <div>
              <div className="flex items-end gap-3">
                <ShieldCheck size={28} className="text-accent" />
                <p className="text-[40px] font-semibold leading-none tracking-tight">{data.quality.score?.toFixed(0)}</p>
                <p className="pb-1 text-sm text-ink-2">out of 100 (grade {data.quality.grade})</p>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge tone={data.quality.critical ? 'critical' : 'good'}>{data.quality.critical} critical</Badge>
                <Badge tone={data.quality.warnings ? 'warning' : 'good'}>{data.quality.warnings} warnings</Badge>
              </div>
              <p className="mt-3 text-sm text-ink-2">{dataset?.valid_row_count.toLocaleString()} of {dataset?.row_count.toLocaleString()} rows feed the analytics. Issues are reported, never silently corrected.</p>
            </div>
          )}
        </Panel>
      </div>

      {data && data.products.length > 0 && (
        <Panel title="Top products" subtitle="Ranked by revenue for the selected period. Click a row to filter.">
          <DataTable rows={data.products} rowKey={(r) => r.key} selectedKeys={filters.product} onRowClick={(r) => toggleFilter('product', r.key)}
            initialSort={{ key: 'revenue', dir: 'desc' }}
            columns={[{ key: 'key', label: dimLabel('product'), format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' },
              { key: 'share', label: 'Share', format: 'percent' }, { key: 'units', label: 'Units', format: 'number' },
              { key: 'profit', label: 'Profit', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' },
              { key: 'growth', label: 'Growth', format: 'signed' }]} />
        </Panel>
      )}
    </div>
  );
}
