import { ChartCard } from '../components/charts/ChartCard';
import { DonutChart, GroupedColumns, TrendChart } from '../components/charts/charts';
import { InsightList } from '../components/insights/InsightCard';
import { KpiStrip } from '../components/kpi/KpiStrip';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { Callout, ErrorNote, Panel } from '../components/ui/primitives';
import { fmtChange } from '../lib/format';
import { useModule } from '../lib/useModule';
import { useApp } from '../state/AppState';
import type { Overview } from './Dashboard';

export default function Executive() {
  const { filters, toggleFilter, setFilters, colorFor, caps, dimLabel } = useApp();
  const { data, loading, error, reload } = useModule<Overview>('overview');
  const attention = data?.kpis.filter((k) => data.attention.includes(k.key)) ?? [];
  const has = (d: string) => !!caps?.filters[d]?.available;
  const regionRows = (data?.regions ?? []).map((r) => ({ key: r.key, current: r.revenue, previous: r.prev_revenue ?? null, growth: r.growth ?? null }));
  return (
    <div className="space-y-5">
      <PageHeader title="Executive overview" meta={<ScopeNote meta={data?.meta} />}
        description="Every headline KPI with its previous-period comparison, the movements that need attention, and the insights behind them." />
      {error && <ErrorNote error={error} onRetry={reload} />}
      <KpiStrip kpis={data?.kpis} comparisonLabel={data?.meta.comparison_label} attention={data?.attention} loading={loading && !!data} />
      {attention.length > 0 && (
        <Callout tone="warning" title={`${attention.length} KPI${attention.length > 1 ? 's' : ''} moved against the business beyond the attention threshold`}>
          {attention.map((k) => `${k.label} ${fmtChange(k.change, k.change_type)}`).join('; ')} vs {data?.meta.comparison_label}.
          Thresholds: ±10% for amounts, ±1 percentage point for ratios.
        </Callout>
      )}
      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-8" title="Revenue against the comparison period" loading={loading} rows={data?.trend.overlay ?? []} height={300}
          subtitle="Click a point to focus on that period"
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'current', label: 'Current', format: 'currency' }, { key: 'previous', label: 'Previous', format: 'currency' }]}>
          <TrendChart data={data?.trend.overlay ?? []} currentLabel={data?.meta.label ?? 'Current'}
            previousLabel={data?.meta.has_comparison ? data.meta.comparison_label : undefined}
            onSelect={(row) => {
              const start = row.period as string;
              if (!start || data?.granularity !== 'month') return;
              const d = new Date(`${start}T00:00:00`);
              const end = new Date(d.getFullYear(), d.getMonth() + 1, 0);
              setFilters((f) => ({ ...f, start_date: start, end_date: `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, '0')}-${String(end.getDate()).padStart(2, '0')}` }));
            }} />
        </ChartCard>
        {has('channel') && (
          <ChartCard className="xl:col-span-4" title={`Revenue by ${dimLabel('channel').toLowerCase()}`} loading={loading} rows={data?.channels ?? []} height={300}
            columns={[{ key: 'key', label: dimLabel('channel'), format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }]}>
            <DonutChart rows={data?.channels ?? []} colorFor={(k) => colorFor('channel', k)} selected={filters.channel} onSelect={(k) => toggleFilter('channel', k)} />
          </ChartCard>
        )}
      </div>
      <div className="grid gap-5 xl:grid-cols-12">
        {has('region') && (
          <ChartCard className={has('customer_segment') ? 'xl:col-span-7' : 'xl:col-span-12'} title="Regional revenue, current vs previous" subtitle="Click a region to filter" loading={loading} rows={regionRows} height={280}
            columns={[{ key: 'key', label: 'Region', format: 'text' }, { key: 'current', label: 'Current', format: 'currency' }, { key: 'previous', label: 'Previous', format: 'currency' }, { key: 'growth', label: 'Growth', format: 'percent' }]}>
            <GroupedColumns rows={regionRows} currentLabel={data?.meta.label ?? 'Current'} previousLabel={data?.meta.has_comparison ? data.meta.comparison_label : undefined}
              selected={filters.region} onSelect={(k) => toggleFilter('region', k)} />
          </ChartCard>
        )}
        {has('customer_segment') && (
          <ChartCard className="xl:col-span-5" title={`Profit by ${dimLabel('customer_segment').toLowerCase()}`} loading={loading} rows={data?.segments ?? []} height={280}
            columns={[{ key: 'key', label: 'Segment', format: 'text' }, { key: 'profit', label: 'Profit', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }]}>
            <DonutChart rows={data?.segments ?? []} valueKey="profit" centerLabel="Profit" colorFor={(k) => colorFor('customer_segment', k)}
              selected={filters.customer_segment} onSelect={(k) => toggleFilter('customer_segment', k)} />
          </ChartCard>
        )}
      </div>
      <Panel title="Business insights" subtitle="Statistical observation and supporting metrics, then the interpretation and recommended action">
        <InsightList insights={data?.insights} />
      </Panel>
    </div>
  );
}
