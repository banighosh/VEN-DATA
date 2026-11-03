import { ChartCard } from '../components/charts/ChartCard';
import { DonutChart, ParetoChart, ScatterPlot, StackedColumns } from '../components/charts/charts';
import { DataTable } from '../components/data/DataTable';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { Badge, Callout, ErrorNote, NotSupported, Panel, Stat } from '../components/ui/primitives';
import { fmtCurrency, fmtDate, fmtNumber, fmtPercent } from '../lib/format';
import { navigate } from '../lib/hooks';
import type { BreakdownRow, ScopeMeta } from '../lib/types';
import { useModule } from '../lib/useModule';
import { useApp } from '../state/AppState';

interface Account extends BreakdownRow { tier: string; cumulative_share: number; first_purchase: string; last_purchase: string; lifetime_revenue: number; status: string }
interface CustData {
  meta: ScopeMeta; available: boolean; reason?: string; requires?: string[]; label: string; key: string;
  summary: { total: number; new: number; returning: number; previous_total: number | null; retained: number | null; retention_rate: number | null;
    churned: number | null; avg_transactions: number | null; avg_days_between_purchases: number | null; avg_revenue_per_customer: number | null;
    top_customer_share: number | null; known_customers: number };
  new_vs_returning: { label: string; new: number; returning: number; active: number }[];
  segments: BreakdownRow[]; segment_label: string; accounts: Account[]; pareto: { key: string; share: number | null; cumulative_share: number }[];
  clv: { available: boolean; method: string; reason?: string; avg_lifetime_revenue?: number; avg_lifetime_profit?: number | null; avg_lifespan_days?: number; note?: string };
}

export default function Customers() {
  const { colorFor, filters, toggleFilter, chart, caps } = useApp();
  const { data, loading, error, reload } = useModule<CustData>('customers');
  if (data && !data.available) {
    return (
      <div className="space-y-5">
        <PageHeader title="Customer analytics" />
        <NotSupported title="Customer analytics needs a customer column" reason={data.reason ?? ''} requires={data.requires} onMap={() => navigate('data')} />
      </div>
    );
  }
  const label = data?.label ?? 'Customer';
  const lower = label.toLowerCase();
  const s = data?.summary;
  const tierColor = (t: string) => (t === 'A' ? chart.series[0] : t === 'B' ? chart.series[1] : chart.series[2]);
  const nvr = { keys: ['New', 'Returning'], rows: (data?.new_vs_returning ?? []).map((r) => ({ label: r.label, New: r.new, Returning: r.returning })) };
  return (
    <div className="space-y-5">
      <PageHeader title="Customer analytics" meta={<ScopeNote meta={data?.meta} />}
        description={`Who buys, how often they come back, which segments are most profitable and how concentrated revenue is across ${lower}s.`} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {data && caps?.fields.customer_name?.source && /retailer|account|client/i.test(caps.fields.customer_name.source) && (
        <Callout tone="info" title={`Customers are ${lower}s in this dataset`}>
          There is no individual customer field, so each value of the “{caps.fields.customer_name.source}” column is treated as a customer account.
          With {s?.known_customers} accounts, figures describe account behaviour, not consumer behaviour.
        </Callout>
      )}

      <Panel loading={loading} bodyClass="px-5 py-5">
        <div className="grid grid-cols-2 gap-x-6 gap-y-5 md:grid-cols-4 xl:grid-cols-7">
          <Stat label={`Active ${lower}s`} value={fmtNumber(s?.total)} hint={s?.previous_total !== null && s?.previous_total !== undefined ? `${s.previous_total} in ${data?.meta.comparison_label}` : undefined} />
          <Stat label="New" value={fmtNumber(s?.new)} hint="First purchase in this period" />
          <Stat label="Returning" value={fmtNumber(s?.returning)} hint="Bought before this period" />
          <Stat label="Retention rate" value={fmtPercent(s?.retention_rate)} hint={s?.retained !== null && s?.retained !== undefined ? `${s.retained} of ${s.previous_total} kept` : 'Needs a comparison period'} />
          <Stat label="Purchase frequency" value={fmtNumber(s?.avg_transactions, true, 0)} hint={`Transactions per ${lower}`} />
          <Stat label="Days between purchases" value={fmtNumber(s?.avg_days_between_purchases, true, 1)} hint="Average gap per account" />
          <Stat label={`Revenue per ${lower}`} value={fmtCurrency(s?.avg_revenue_per_customer)} hint="In this period" />
        </div>
      </Panel>

      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-7" title={`New vs returning ${lower}s`} subtitle={`Active ${lower}s per period, split by whether it was their first purchase`}
          loading={loading} rows={nvr.rows} height={280}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, { key: 'New', label: 'New', format: 'number' }, { key: 'Returning', label: 'Returning', format: 'number' }]}>
          <StackedColumns pivot={nvr} format="number" colorFor={(k) => (k === 'New' ? chart.series[1] : chart.series[0])} />
        </ChartCard>
        {data && data.segments.length > 0 && (
          <ChartCard className="xl:col-span-5" title={`Profit by ${data.segment_label.toLowerCase()}`} subtitle="Customer segmentation. Click to filter"
            loading={loading} rows={data.segments} height={280}
            columns={[{ key: 'key', label: data.segment_label, format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'profit', label: 'Profit', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }]}>
            <DonutChart rows={data.segments} valueKey="profit" centerLabel="Profit" colorFor={(k) => colorFor('customer_segment', k)}
              selected={filters.customer_segment} onSelect={(k) => toggleFilter('customer_segment', k)} />
          </ChartCard>
        )}
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <ChartCard title="Revenue concentration" subtitle={`Share of revenue by ${lower}, with the cumulative share. Click a bar to filter.`}
          loading={loading} rows={data?.pareto ?? []} height={280}
          columns={[{ key: 'key', label, format: 'text' }, { key: 'share', label: 'Share', format: 'percent' }, { key: 'cumulative_share', label: 'Cumulative', format: 'percent' }]}>
          <ParetoChart rows={data?.pareto ?? []} onSelect={(k) => toggleFilter('customer', k)} />
        </ChartCard>
        <ChartCard title={`${label} value and profitability`} subtitle="Revenue against margin; bubble size is transactions; colour is value tier"
          loading={loading} rows={data?.accounts ?? []} height={280}
          columns={[{ key: 'key', label, format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'tier', label: 'Tier', format: 'text' }]}>
          <ScatterPlot points={(data?.accounts ?? []).filter((a) => a.revenue > 0).map((a) => ({ key: a.key, x: a.revenue, y: a.margin ?? 0, z: a.transactions, group: `Tier ${a.tier}` }))}
            xLabel="Revenue" yLabel="Margin" zLabel="Transactions" colorFor={(g) => tierColor(g.replace('Tier ', ''))} onSelect={(k) => toggleFilter('customer', k)} labelTop={6} />
        </ChartCard>
      </div>

      <Panel title={`${label} accounts`} subtitle="Tier A accounts make up the first 80% of revenue; B the next 15%; C the rest. Click a row to filter." loading={loading}>
        <DataTable rows={data?.accounts ?? []} rowKey={(r) => r.key} selectedKeys={filters.customer} onRowClick={(r) => toggleFilter('customer', r.key)}
          initialSort={{ key: 'revenue', dir: 'desc' }}
          columns={[{ key: 'key', label, format: 'text' },
            { key: 'status', label: 'Status', format: 'text', render: (r) => <Badge tone={r.status === 'New' ? 'info' : r.status === 'Lapsed' ? 'warning' : 'neutral'}>{r.status}</Badge> },
            { key: 'tier', label: 'Tier', format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'share', label: 'Share', format: 'percent' },
            { key: 'profit', label: 'Profit', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'transactions', label: 'Transactions', format: 'number' },
            { key: 'growth', label: 'Growth', format: 'signed' }, { key: 'lifetime_revenue', label: 'Lifetime revenue', format: 'currency' },
            { key: 'first_purchase', label: 'First purchase', format: 'date', render: (r) => fmtDate(r.first_purchase) },
            { key: 'last_purchase', label: 'Last purchase', format: 'date', render: (r) => fmtDate(r.last_purchase) }]} />
      </Panel>

      <Panel title="Customer lifetime value">
        {data?.clv.available ? (
          <div className="grid gap-5 sm:grid-cols-3">
            <Stat label="Average lifetime revenue" value={fmtCurrency(data.clv.avg_lifetime_revenue)} hint={data.clv.note} />
            <Stat label="Average lifetime profit" value={fmtCurrency(data.clv.avg_lifetime_profit)} />
            <Stat label="Average customer lifespan" value={`${fmtNumber(data.clv.avg_lifespan_days)} days`} />
          </div>
        ) : (
          <p className="max-w-3xl text-sm text-ink-2">{data?.clv.reason}</p>
        )}
      </Panel>
    </div>
  );
}
