import { useMemo, useState } from 'react';
import { ChartCard } from '../components/charts/ChartCard';
import { BarList, DonutChart, MultiLine, ScatterPlot, StackedColumns } from '../components/charts/charts';
import { DrillBreakdown } from '../components/charts/DrillBreakdown';
import { Heatmap } from '../components/charts/Heatmap';
import { DataTable } from '../components/data/DataTable';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { Badge, ErrorNote, NotSupported, Panel, Segmented } from '../components/ui/primitives';
import { fmtPercent } from '../lib/format';
import { navigate } from '../lib/hooks';
import type { BreakdownRow, Matrix, Pivot, ScopeMeta } from '../lib/types';
import { useModule } from '../lib/useModule';
import { useApp } from '../state/AppState';

interface ProductRow extends BreakdownRow { category: string | null; trend_slope: number | null }
interface ProdData {
  meta: ScopeMeta; available: boolean; reason?: string; requires?: string[];
  products: ProductRow[]; best: ProductRow[]; worst: ProductRow[]; most_profitable: ProductRow[]; least_profitable: ProductRow[];
  declining: ProductRow[]; categories: BreakdownRow[]; subcategories: BreakdownRow[]; trend: Pivot; category_trend: Pivot; heatmap: Matrix;
}

export default function Products() {
  const { colorFor, filters, toggleFilter, dimLabel, caps, chart } = useApp();
  const { data, loading, error, reload } = useModule<ProdData>('products');
  const [rank, setRank] = useState<'best' | 'worst' | 'most_profitable' | 'least_profitable'>('best');
  const [stackPct, setStackPct] = useState(false);
  const rankRows = data?.[rank] ?? [];
  const rankMetric = rank.includes('profitable') ? 'margin' : 'revenue';
  const catsForScatter = useMemo(() => [...new Set((data?.products ?? []).map((p) => p.category ?? 'All'))], [data]);
  if (data && !data.available) {
    return (<div className="space-y-5"><PageHeader title="Product analytics" />
      <NotSupported title="Product analytics needs a product column" reason={data.reason ?? ''} requires={data.requires} onMap={() => navigate('data')} /></div>);
  }
  const hasCat = !!caps?.filters.category?.available;
  return (
    <div className="space-y-5">
      <PageHeader title="Product and category analytics" meta={<ScopeNote meta={data?.meta} />}
        description="Best and worst performers, what each category contributes, which products earn their keep, and which are losing ground." />
      {error && <ErrorNote error={error} onRetry={reload} />}

      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-7" title="Product ranking" loading={loading} rows={rankRows} height={300}
          subtitle={rankMetric === 'margin' ? 'Ranked by profit margin' : 'Ranked by revenue'}
          controls={<Segmented value={rank} onChange={setRank} label="Ranking" options={[
            { value: 'best', label: 'Top revenue' }, { value: 'worst', label: 'Lowest revenue' },
            { value: 'most_profitable', label: 'Highest margin' }, { value: 'least_profitable', label: 'Lowest margin' }]} />}
          columns={[{ key: 'key', label: 'Product', format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'growth', label: 'Growth', format: 'signed' }]}>
          <BarList rows={rankRows} valueKey={rankMetric} format={rankMetric === 'margin' ? 'percent' : 'currency'} selected={filters.product}
            colorFor={(k) => colorFor('product', k)} secondary={rankMetric === 'margin' ? { key: 'revenue', label: 'Revenue', format: 'currency' } : { key: 'margin', label: 'Margin', format: 'percent' }}
            onSelect={(k) => toggleFilter('product', k)} />
        </ChartCard>
        {hasCat && (
          <ChartCard className="xl:col-span-5" title="Category contribution" subtitle="Share of revenue. Click to filter" loading={loading} rows={data?.categories ?? []} height={300}
            columns={[{ key: 'key', label: 'Category', format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'share', label: 'Share', format: 'percent' }, { key: 'margin', label: 'Margin', format: 'percent' }]}>
            <DonutChart rows={data?.categories ?? []} colorFor={(k) => colorFor('category', k)} selected={filters.category} onSelect={(k) => toggleFilter('category', k)} />
          </ChartCard>
        )}
      </div>

      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-6" title="Product profitability" subtitle="Revenue against margin; bubble size is units sold. Click a point to filter"
          loading={loading} rows={data?.products ?? []} height={300}
          columns={[{ key: 'key', label: 'Product', format: 'text' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'units', label: 'Units', format: 'number' }]}>
          <ScatterPlot points={(data?.products ?? []).filter((p) => p.revenue > 0).map((p) => ({ key: p.key, x: p.revenue, y: p.margin ?? 0, z: p.units ?? 1, group: catsForScatter.length <= 3 ? p.category ?? 'All' : 'All' }))}
            xLabel="Revenue" yLabel="Margin" zLabel="Units" colorFor={(g) => (g === 'All' ? chart.series[0] : colorFor('category', g))} onSelect={(k) => toggleFilter('product', k)} labelTop={6} />
        </ChartCard>
        <ChartCard className="xl:col-span-6" title="Product growth trends" subtitle="Monthly revenue per product. Hover a name to highlight it"
          loading={loading} rows={data?.trend.rows ?? []} height={300}
          columns={[{ key: 'label', label: 'Period', format: 'text' }, ...(data?.trend.keys ?? []).map((k) => ({ key: k, label: k, format: 'currency' as const }))]}>
          {data && <MultiLine pivot={data.trend} colorFor={(k) => colorFor('product', k)} onSelectKey={(k) => toggleFilter('product', k)} />}
        </ChartCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-12">
        {hasCat && data && data.category_trend.keys.length > 0 && (
          <ChartCard className="xl:col-span-7" title="Category revenue distribution over time" loading={loading} rows={data.category_trend.rows} height={280}
            controls={<Segmented value={stackPct ? 'pct' : 'abs'} onChange={(v) => setStackPct(v === 'pct')} label="Scale" options={[{ value: 'abs', label: '$' }, { value: 'pct', label: '%' }]} />}
            columns={[{ key: 'label', label: 'Period', format: 'text' }, ...data.category_trend.keys.map((k) => ({ key: k, label: k, format: 'currency' as const }))]}>
            <StackedColumns pivot={data.category_trend} percent={stackPct} colorFor={(k) => colorFor('category', k)} onSelectKey={(k) => toggleFilter('category', k)} />
          </ChartCard>
        )}
        <DrillBreakdown className={hasCat ? 'xl:col-span-5' : 'xl:col-span-12'} title="Product hierarchy" chain={['category', 'subcategory', 'product']} />
      </div>

      {data && data.heatmap.rows.length > 0 && (
        <ChartCard title={`Product × ${data.heatmap.cols.length && caps?.filters.channel?.available ? dimLabel('channel').toLowerCase() : 'region'} ${data.heatmap.measure === 'margin' ? 'margin' : 'revenue'}`}
          subtitle="Performance pattern across the matrix. Click a row to filter by product" loading={loading}
          rows={data.heatmap.cells as unknown as Record<string, unknown>[]} height={Math.max(160, data.heatmap.rows.length * 32 + 60)}
          columns={[{ key: 'row', label: 'Product', format: 'text' }, { key: 'col', label: 'Segment', format: 'text' }, { key: 'value', label: 'Value', format: data.heatmap.measure === 'margin' ? 'percent' : 'currency' }]}>
          <Heatmap matrix={data.heatmap} format={data.heatmap.measure === 'margin' ? 'percent' : 'currency'} onSelectRow={(r) => toggleFilter('product', r)} />
        </ChartCard>
      )}

      <Panel title="All products" subtitle={data?.declining.length ? `${data.declining.length} product(s) are declining (negative growth or a falling monthly trend).` : 'No product is declining in the selected period.'} loading={loading}>
        <DataTable rows={data?.products ?? []} rowKey={(r) => r.key} selectedKeys={filters.product} onRowClick={(r) => toggleFilter('product', r.key)} initialSort={{ key: 'revenue', dir: 'desc' }}
          columns={[{ key: 'key', label: 'Product', format: 'text' }, { key: 'category', label: 'Category', format: 'text' },
            { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'share', label: 'Share', format: 'percent' }, { key: 'units', label: 'Units', format: 'number' },
            { key: 'profit', label: 'Profit', format: 'currency' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'growth', label: 'Growth', format: 'signed' },
            { key: 'trend_slope', label: 'Monthly trend', format: 'text', sortValue: (r) => r.trend_slope,
              render: (r) => r.trend_slope === null ? <span className="text-ink-3">—</span>
                : <Badge tone={r.trend_slope < -0.03 ? 'warning' : r.trend_slope > 0.03 ? 'good' : 'neutral'}>{fmtPercent(r.trend_slope, 1, true)} / month</Badge> }]} />
      </Panel>
    </div>
  );
}
