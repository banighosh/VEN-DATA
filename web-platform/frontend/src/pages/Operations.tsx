import { ChartCard } from '../components/charts/ChartCard';
import { BarList, ColumnChart, TrendChart } from '../components/charts/charts';
import { Heatmap } from '../components/charts/Heatmap';
import { DataTable } from '../components/data/DataTable';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { ErrorNote, NotSupported, Panel, Stat } from '../components/ui/primitives';
import { fmtChange, fmtCurrency, fmtNumber, fmtPercent } from '../lib/format';
import { navigate } from '../lib/hooks';
import type { BreakdownRow, Matrix, ScopeMeta } from '../lib/types';
import { useModule } from '../lib/useModule';
import { useApp } from '../state/AppState';

interface Avail { available: boolean; reason?: string; requires?: string[]; [k: string]: unknown }
interface OpsData {
  meta: ScopeMeta; granularity: string;
  summary: { transactions: number; prev_transactions: number | null; orders: number; units: number | null; prev_units: number | null;
    units_per_txn: number | null; prev_units_per_txn: number | null; revenue_per_unit: number | null; prev_revenue_per_unit: number | null;
    active_days: number; txn_per_active_day: number | null };
  volume: { label: string; transactions: number; units: number | null; units_per_txn: number | null }[];
  weekday_heatmap: Matrix;
  channel_efficiency: (BreakdownRow & { units_per_txn: number | null; revenue_per_unit: number | null; profit_per_unit: number | null })[];
  processing_time: Avail; delivery: Avail; cancellations: Avail; fulfilment: Avail;
}

const delta = (cur: number | null | undefined, prev: number | null | undefined) =>
  cur !== null && cur !== undefined && prev ? fmtChange((cur - prev) / Math.abs(prev), 'relative') : undefined;

export default function Operations() {
  const { filters, toggleFilter, dimLabel } = useApp();
  const { data, loading, error, reload } = useModule<OpsData>('operations');
  const s = data?.summary;
  const cmp = data?.meta.comparison_label;
  const hint = (cur: number | null | undefined, prev: number | null | undefined) => { const d = delta(cur, prev); return d && cmp ? `${d} vs ${cmp}` : undefined; };
  const unavailable = [
    { title: 'Order processing time', a: data?.processing_time },
    { title: 'Delivery performance', a: data?.delivery },
    { title: 'Cancellation rate', a: data?.cancellations },
    { title: 'Fulfilment performance', a: data?.fulfilment },
  ].filter((x) => x.a && !x.a.available);
  return (
    <div className="space-y-5">
      <PageHeader title="Operational analytics" meta={<ScopeNote meta={data?.meta} />}
        description="Order volume, throughput and channel efficiency. Fulfilment, delivery and cancellation metrics appear only when the data contains the fields they need." />
      {error && <ErrorNote error={error} onRetry={reload} />}

      <Panel loading={loading} bodyClass="px-5 py-5">
        <div className="grid grid-cols-2 gap-6 md:grid-cols-3 xl:grid-cols-5">
          <Stat label="Order volume" value={fmtNumber(s?.transactions)} hint={hint(s?.transactions, s?.prev_transactions) ?? 'Transaction lines'} />
          <Stat label="Units sold" value={fmtNumber(s?.units)} hint={hint(s?.units, s?.prev_units)} />
          <Stat label="Units per transaction" value={fmtNumber(s?.units_per_txn, true, 1)} hint={hint(s?.units_per_txn, s?.prev_units_per_txn)} />
          <Stat label="Revenue per unit" value={fmtCurrency(s?.revenue_per_unit)} hint={hint(s?.revenue_per_unit, s?.prev_revenue_per_unit)} />
          <Stat label="Transactions per active day" value={fmtNumber(s?.txn_per_active_day, true, 1)} hint={s ? `${s.active_days} active selling days` : undefined} />
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-2">
        <ChartCard title="Order volume" subtitle="Transactions per period" loading={loading} rows={data?.volume ?? []} height={260}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'transactions', label: 'Transactions', format: 'number' }, { key: 'units', label: 'Units', format: 'number' }]}>
          <ColumnChart data={data?.volume ?? []} dataKey="transactions" format="number" name="Transactions" />
        </ChartCard>
        <ChartCard title="Units per transaction" subtitle="Average basket depth per period (operational efficiency)" loading={loading}
          rows={data?.volume ?? []} height={260}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'units_per_txn', label: 'Units per transaction', format: 'number' }]}>
          <TrendChart data={(data?.volume ?? []).map((v) => ({ label: v.label, current: v.units_per_txn, previous: null }))} format="number" currentLabel="Units per transaction" />
        </ChartCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-12">
        {data && data.weekday_heatmap.rows.length > 0 && (
          <ChartCard className="xl:col-span-7" title="When orders happen" subtitle="Transactions by weekday and month of year" loading={loading}
            rows={data.weekday_heatmap.cells as unknown as Record<string, unknown>[]} height={300}
            columns={[{ key: 'row', label: 'Weekday', format: 'text' }, { key: 'col', label: 'Month', format: 'text' }, { key: 'value', label: 'Transactions', format: 'number' }]}>
            <Heatmap matrix={data.weekday_heatmap} format="number" />
          </ChartCard>
        )}
        {data && data.channel_efficiency.length > 0 && (
          <ChartCard className="xl:col-span-5" title={`Revenue per unit by ${dimLabel('channel').toLowerCase()}`} subtitle="Click to filter" loading={loading}
            rows={data.channel_efficiency} height={Math.max(150, data.channel_efficiency.length * 30 + 16)}
            columns={[{ key: 'key', label: dimLabel('channel'), format: 'text' }, { key: 'revenue_per_unit', label: 'Revenue per unit', format: 'currency' }, { key: 'units_per_txn', label: 'Units per transaction', format: 'number' }]}>
            <BarList rows={data.channel_efficiency} valueKey="revenue_per_unit" selected={filters.channel} onSelect={(k) => toggleFilter('channel', k)}
              secondary={{ key: 'units_per_txn', label: 'Units per transaction', format: 'number' }} />
          </ChartCard>
        )}
      </div>

      {data && data.channel_efficiency.length > 0 && (
        <Panel title="Channel efficiency" subtitle="Throughput and unit economics by sales channel">
          <DataTable rows={data.channel_efficiency} rowKey={(r) => r.key} selectedKeys={filters.channel} onRowClick={(r) => toggleFilter('channel', r.key)} initialSort={{ key: 'revenue', dir: 'desc' }}
            columns={[{ key: 'key', label: dimLabel('channel'), format: 'text' }, { key: 'transactions', label: 'Transactions', format: 'number' },
              { key: 'units', label: 'Units', format: 'number' }, { key: 'units_per_txn', label: 'Units / transaction', format: 'number' },
              { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'revenue_per_unit', label: 'Revenue / unit', format: 'currency' },
              { key: 'profit_per_unit', label: 'Profit / unit', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'share', label: 'Share', format: 'percent' }]} />
        </Panel>
      )}

      {data && (['processing_time', 'delivery', 'cancellations'] as const).some((k) => data[k].available) && (
        <Panel title="Fulfilment">
          <div className="grid gap-5 md:grid-cols-3">
            {data.processing_time.available && <Stat label="Avg processing time" value={`${fmtNumber(data.processing_time.avg_days as number, true, 1)} days`} hint={`Median ${fmtNumber(data.processing_time.median_days as number, true, 1)}, P90 ${fmtNumber(data.processing_time.p90_days as number, true, 1)}`} />}
            {data.delivery.available && <Stat label="Avg delivery time" value={`${fmtNumber(data.delivery.avg_days as number, true, 1)} days`} hint={`P90 ${fmtNumber(data.delivery.p90_days as number, true, 1)} days`} />}
            {data.cancellations.available && <Stat label="Cancellation rate" value={fmtPercent(data.cancellations.cancellation_rate as number)} hint={`Return rate ${fmtPercent(data.cancellations.return_rate as number)}`} />}
          </div>
        </Panel>
      )}

      {unavailable.length > 0 && (
        <Panel title="Metrics this dataset cannot support" subtitle="Shown instead of estimates. Map the listed columns on upload to switch them on.">
          <div className="grid gap-3 md:grid-cols-2">
            {unavailable.map((u) => <NotSupported key={u.title} title={u.title} reason={u.a!.reason ?? ''} requires={u.a!.requires} />)}
          </div>
          <button onClick={() => navigate('data')} className="mt-3 text-sm font-medium text-accent-ink hover:underline">Go to Data Management</button>
        </Panel>
      )}
    </div>
  );
}
