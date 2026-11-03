import { useMemo, useState } from 'react';
import { ChartCard, type Crumb } from '../components/charts/ChartCard';
import { ColumnChart, CumulativeArea, ForecastChart, StackedColumns, TrendChart } from '../components/charts/charts';
import { DataTable } from '../components/data/DataTable';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { Callout, ErrorNote, Panel, Segmented, Select } from '../components/ui/primitives';
import { fmtPercent } from '../lib/format';
import type { BreakdownRow, Pivot, ScopeMeta, SeriesPoint } from '../lib/types';
import { useModule } from '../lib/useModule';
import { useApp } from '../state/AppState';

type Gran = 'year' | 'quarter' | 'month' | 'week' | 'day';

interface PerfData {
  meta: ScopeMeta;
  trend: {
    granularity: string; series: SeriesPoint[]; previous_series: SeriesPoint[];
    overlay: { label: string; period: string; current: number | null; previous: number | null; previous_label: string | null }[];
    growth: { label: string; period: string; pop: number | null; yoy: number | null }[];
    cumulative: { label: string; current: number | null; previous: number | null }[];
  };
  quarterly: (SeriesPoint & { pop_growth: number | null; yoy_growth: number | null })[];
  annual: (SeriesPoint & { pop_growth: number | null; yoy_growth: number | null })[];
  contribution: Pivot & { dimension: string | null; label: string | null };
  segments: Record<string, { label: string; rows: BreakdownRow[] }>;
}

interface ForecastData {
  available: boolean; reason?: string; method?: string; mape?: number | null; warnings?: string[]; label?: string;
  history: { label: string; actual: number }[]; forecast?: { label: string; forecast: number; lower: number; upper: number }[];
}

const lastDay = (y: number, m: number) => new Date(y, m + 1, 0).getDate();

export default function Performance() {
  const { filters, setFilters, colorFor, caps, dimLabel } = useApp();
  const [gran, setGran] = useState<Gran>('month');
  const [growthMode, setGrowthMode] = useState<'pop' | 'yoy'>('yoy');
  const [split, setSplit] = useState<string>('channel');
  const [pct, setPct] = useState(false);
  const [table, setTable] = useState<'annual' | 'quarterly'>('quarterly');
  const splitOptions = ['channel', 'category', 'region', 'customer_segment', 'business_unit', 'product'].filter((d) => caps?.filters[d]?.available);
  const splitBy = splitOptions.includes(split) ? split : splitOptions[0];
  const { data, loading, error, reload } = useModule<PerfData>('performance', { granularity: gran, split_by: splitBy });
  const fc = useModule<ForecastData>('forecast', { horizon: 6 });
  const prevLabel = data?.meta.has_comparison ? data.meta.comparison_label : undefined;

  const margin = useMemo(() => (data?.trend.series ?? []).map((s, i) => ({
    label: s.label, current: s.margin ?? null, previous: data?.trend.previous_series[i]?.margin ?? null,
    previous_label: data?.trend.previous_series[i]?.label ?? null,
  })), [data]);

  // Time drill: clicking a year narrows to that year (quarters); a quarter narrows to its months.
  const drillTime = (row: Record<string, unknown>) => {
    const start = String(row.period);
    const [y, m] = start.split('-').map(Number);
    if (gran === 'year') { setFilters((f) => ({ ...f, start_date: `${y}-01-01`, end_date: `${y}-12-31` })); setGran('quarter'); }
    else if (gran === 'quarter') {
      const em = m - 1 + 2;
      setFilters((f) => ({ ...f, start_date: start, end_date: `${y}-${String(em + 1).padStart(2, '0')}-${lastDay(y, em)}` })); setGran('month');
    }
  };
  const crumbs: Crumb[] = [{ label: 'All years', onClick: () => { setFilters((f) => ({ ...f, start_date: null, end_date: null })); setGran('year'); } }];
  if (filters.start_date) crumbs.push({ label: data?.meta.label ?? filters.start_date });

  const growthRows = (data?.trend.growth ?? []).map((g) => ({ label: g.label, period: g.period, value: growthMode === 'pop' ? g.pop : g.yoy }));
  const periodCols = [{ key: 'label', label: 'Period', format: 'text' as const }, { key: 'revenue', label: 'Revenue', format: 'currency' as const },
    { key: 'profit', label: 'Profit', format: 'currency' as const }, { key: 'margin', label: 'Margin', format: 'percent' as const },
    { key: 'units', label: 'Units', format: 'number' as const }, { key: 'transactions', label: 'Transactions', format: 'number' as const },
    { key: 'pop_growth', label: 'vs prior period', format: 'signed' as const }, { key: 'yoy_growth', label: 'vs prior year', format: 'signed' as const }];

  return (
    <div className="space-y-5">
      <PageHeader title="Business performance" meta={<ScopeNote meta={data?.meta} />}
        description="Monthly, quarterly and annual results, growth, profitability and what each segment contributes."
        actions={<Segmented label="Granularity" size="md" value={gran} onChange={setGran}
          options={[{ value: 'year', label: 'Year' }, { value: 'quarter', label: 'Quarter' }, { value: 'month', label: 'Month' }, { value: 'week', label: 'Week' }]} />} />
      {error && <ErrorNote error={error} onRetry={reload} />}

      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-7" title="Revenue trend" subtitle="Current period against the comparison period, aligned by position"
          loading={loading} rows={data?.trend.overlay ?? []} height={300}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'current', label: 'Current', format: 'currency' }, { key: 'previous', label: 'Previous', format: 'currency' }, { key: 'previous_label', label: 'Previous period', format: 'text' }]}>
          <TrendChart data={data?.trend.overlay ?? []} currentLabel={data?.meta.label ?? 'Current'} previousLabel={prevLabel} />
        </ChartCard>
        <ChartCard className="xl:col-span-5" title={`Revenue by ${gran}`} crumbs={crumbs}
          subtitle={gran === 'year' || gran === 'quarter' ? 'Click a bar to drill into it' : `Showing ${gran}s; switch to Year or Quarter to drill`}
          loading={loading} rows={(data?.trend.series ?? []) as unknown as Record<string, unknown>[]} height={300}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'transactions', label: 'Transactions', format: 'number' }]}>
          <ColumnChart data={(data?.trend.series ?? []) as unknown as Record<string, unknown>[]} dataKey="revenue" name="Revenue"
            onSelect={gran === 'year' || gran === 'quarter' ? drillTime : undefined} />
        </ChartCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <ChartCard title="Revenue growth" loading={loading} rows={growthRows} height={260}
          subtitle={growthMode === 'yoy' ? 'Each period against the same period a year earlier' : 'Each period against the one before it'}
          controls={<Segmented value={growthMode} onChange={setGrowthMode} label="Growth basis" options={[{ value: 'yoy', label: 'vs last year' }, { value: 'pop', label: 'vs prior period' }]} />}
          empty={growthRows.every((g) => g.value === null) ? 'No earlier periods in the data to compare against.' : undefined}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'value', label: 'Growth', format: 'signed' }]}>
          <ColumnChart data={growthRows} dataKey="value" format="percent" signed name="Growth" />
        </ChartCard>
        <ChartCard title="Cumulative revenue" subtitle="Running total through the period" loading={loading} rows={data?.trend.cumulative ?? []} height={260}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'current', label: 'Current', format: 'currency' }, { key: 'previous', label: 'Previous', format: 'currency' }]}>
          <CumulativeArea data={data?.trend.cumulative ?? []} currentLabel={data?.meta.label ?? 'Current'} previousLabel={prevLabel} />
        </ChartCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-12">
        {data?.contribution.dimension && (
          <ChartCard className="xl:col-span-7" title={`Sales contribution by ${dimLabel(data.contribution.dimension).toLowerCase()}`} loading={loading}
            subtitle="Click a segment to filter" rows={data.contribution.rows} height={300}
            controls={<>
              <Select label="Split by" value={splitBy} onChange={setSplit} options={splitOptions.map((d) => ({ value: d, label: dimLabel(d) }))} />
              <Segmented value={pct ? 'pct' : 'abs'} onChange={(v) => setPct(v === 'pct')} label="Scale" options={[{ value: 'abs', label: '$' }, { value: 'pct', label: '%' }]} />
            </>}
            columns={[{ key: 'label', label: 'Period', format: 'text' }, ...data.contribution.keys.map((k) => ({ key: k, label: k, format: 'currency' as const }))]}>
            <StackedColumns pivot={data.contribution} percent={pct} colorFor={(k) => colorFor(data.contribution.dimension!, k)}
              onSelectKey={(k) => k !== 'Other' && setFilters((f) => ({ ...f, [data.contribution.dimension!]: [k] }))} />
          </ChartCard>
        )}
        <ChartCard className="xl:col-span-5" title="Profitability trend" subtitle="Profit margin by period" loading={loading} rows={margin} height={300}
          empty={caps?.metrics.margin?.available ? undefined : 'Margin needs a profit or cost column.'}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'current', label: 'Margin', format: 'percent' }, { key: 'previous', label: 'Previous margin', format: 'percent' }]}>
          <TrendChart data={margin} format="percent" currentLabel={`${data?.meta.label ?? 'Current'} margin`} previousLabel={prevLabel ? `${prevLabel} margin` : undefined} />
        </ChartCard>
      </div>

      <Panel title="Period summary" subtitle="Growth columns use the full history, so the first period of the selection still compares with what came before"
        actions={<Segmented value={table} onChange={setTable} label="Period" options={[{ value: 'quarterly', label: 'Quarterly' }, { value: 'annual', label: 'Annual' }]} />}>
        <DataTable rows={(table === 'annual' ? data?.annual : data?.quarterly) as unknown as Record<string, unknown>[] ?? []} columns={periodCols} dense />
      </Panel>

      {data && Object.keys(data.segments).length > 0 && <Segments segments={data.segments} hasPrev={!!prevLabel} />}

      <ChartCard title="Revenue forecast" subtitle={fc.data?.available ? `${fc.data.method}. ${fc.data.label}.` : 'Statistical projection'}
        loading={fc.loading} rows={[...(fc.data?.history ?? []), ...(fc.data?.forecast ?? [])] as Record<string, unknown>[]} height={280}
        empty={fc.data && !fc.data.available ? fc.data.reason : undefined}
        footnote={fc.data?.mape !== undefined && fc.data?.mape !== null ? `Back-test error (last 3 months held out): ${fmtPercent(fc.data.mape)} MAPE` : undefined}
        columns={[{ key: 'label', label: 'Month', format: 'text' }, { key: 'actual', label: 'Actual', format: 'currency' }, { key: 'forecast', label: 'Forecast', format: 'currency' },
          { key: 'lower', label: 'Low (80%)', format: 'currency' }, { key: 'upper', label: 'High (80%)', format: 'currency' }]}>
        {fc.data?.available && <ForecastChart history={fc.data.history} forecast={fc.data.forecast ?? []} />}
      </ChartCard>
      {fc.data?.warnings?.map((w) => <Callout key={w} tone="warning" title="Forecast caution">{w}</Callout>)}
    </div>
  );
}

function Segments({ segments, hasPrev }: { segments: PerfData['segments']; hasPrev: boolean }) {
  const { toggleFilter, filters } = useApp();
  const keys = Object.keys(segments);
  const [dim, setDim] = useState(keys[0]);
  const active = segments[dim] ? dim : keys[0];
  return (
    <Panel title="Business segment performance" subtitle="Click a row to filter every view to that segment"
      actions={<Segmented value={active} onChange={setDim} label="Segment" options={keys.map((k) => ({ value: k, label: segments[k].label }))} />}>
      <DataTable rows={segments[active].rows} rowKey={(r) => r.key} selectedKeys={filters[active as keyof typeof filters] as string[]}
        onRowClick={(r) => toggleFilter(active as never, r.key)} initialSort={{ key: 'revenue', dir: 'desc' }}
        columns={[{ key: 'key', label: segments[active].label, format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' },
          { key: 'share', label: 'Share', format: 'percent' }, { key: 'profit', label: 'Profit', format: 'currency' },
          { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'transactions', label: 'Transactions', format: 'number' },
          ...(hasPrev ? [{ key: 'growth', label: 'Growth', format: 'signed' as const }, { key: 'margin_change', label: 'Margin change', format: 'pp' as const }] : [])]} />
    </Panel>
  );
}
