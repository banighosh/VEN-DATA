import { useMemo, useState } from 'react';
import { ChartCard } from '../components/charts/ChartCard';
import { BarList, DonutChart, MultiLine, TrendChart, Waterfall } from '../components/charts/charts';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { Callout, cx, ErrorNote, NotSupported, Panel, Select } from '../components/ui/primitives';
import { fmtChange, fmtValue } from '../lib/format';
import { navigate } from '../lib/hooks';
import type { BreakdownRow, ScopeMeta, SeriesPoint } from '../lib/types';
import { useModule } from '../lib/useModule';
import { useApp } from '../state/AppState';

interface Line { key: string; label: string; available: boolean; value?: number; previous?: number | null; change?: number | null; kind?: 'amount' | 'ratio'; note?: string | null }
interface FinData {
  meta: ScopeMeta; statement: Line[]; trend: SeriesPoint[]; granularity: string; cost_is_derived: boolean;
  expense_breakdown: Record<string, { label: string; rows: { key: string; cost: number; share: number | null; cost_ratio: number | null }[] }>;
  waterfall: { name: string; value: number; kind: 'total' | 'delta' }[];
  bridge: { dimension: string; label: string; steps: { name: string; value: number; kind: 'total' | 'delta' }[] } | null;
  budget: { available: boolean; reason?: string; requires?: string[]; series?: { label: string; actual: number | null; budget: number | null }[]; attainment?: number | null };
  margins: Record<string, { label: string; rows: BreakdownRow[] }>;
}

export default function Financial() {
  const { colorFor, caps, toggleFilter, filters, chart } = useApp();
  const bridgeDims = ['category', 'channel', 'region', 'product'].filter((d) => caps?.filters[d]?.available);
  const [bridgeDim, setBridgeDim] = useState(bridgeDims[0] ?? 'category');
  const { data, loading, error, reload } = useModule<FinData>('financial', { dimension: bridgeDim });
  const expenseDims = Object.keys(data?.expense_breakdown ?? {});
  const [expDim, setExpDim] = useState('category');
  const exp = data?.expense_breakdown[expenseDims.includes(expDim) ? expDim : expenseDims[0]];
  const marginDims = Object.keys(data?.margins ?? {});
  const [mDim, setMDim] = useState('channel');
  const marg = data?.margins[marginDims.includes(mDim) ? mDim : marginDims[0]];
  const activeExpDim = expenseDims.includes(expDim) ? expDim : expenseDims[0];
  const activeMDim = marginDims.includes(mDim) ? mDim : marginDims[0];
  const costLabel = data?.statement.find((l) => l.key === 'cost')?.label ?? 'Cost';
  const profitLabel = data?.statement.find((l) => l.key === 'profit')?.label ?? 'Profit';

  const trendPivot = useMemo(() => ({
    keys: ['Revenue', costLabel, profitLabel],
    rows: (data?.trend ?? []).map((t) => ({ label: t.label, period: t.period, Revenue: t.revenue, [costLabel]: t.cost ?? null, [profitLabel]: t.profit ?? null })),
  }), [data, costLabel, profitLabel]);
  const seriesColor = (k: string) => (k === 'Revenue' ? chart.series[0] : k === costLabel ? chart.series[1] : chart.series[2]);

  return (
    <div className="space-y-5">
      <PageHeader title="Financial analytics" meta={<ScopeNote meta={data?.meta} />}
        description="Revenue, cost and profit, how revenue turns into profit, what moved profit between periods, and where cost sits." />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {data?.cost_is_derived && (
        <Callout tone="info" title="Cost is implied, not reported">
          The dataset has no cost column, so cost is shown as revenue minus {profitLabel.toLowerCase()}. It is labelled “{costLabel}” everywhere it appears.
        </Callout>
      )}

      <div className="grid gap-5 xl:grid-cols-12">
        <Panel className="xl:col-span-5" title="Profit and loss summary" subtitle={data?.meta.has_comparison ? `${data.meta.label} compared with ${data.meta.comparison_label}` : data?.meta.label} loading={loading}>
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-xs text-ink-2">
              <th className="py-2 text-left font-medium">Line</th><th className="py-2 pl-4 text-right font-medium">Current</th>
              <th className="py-2 pl-4 text-right font-medium">Previous</th><th className="py-2 pl-4 text-right font-medium">Change</th>
            </tr></thead>
            <tbody className="tnum">
              {(data?.statement ?? []).map((l) => (
                <tr key={l.key} className={cx('border-b border-line last:border-0', l.key === 'profit' && 'font-semibold')}>
                  <td className="py-2.5 pr-2">
                    {l.label}
                    {l.note && <span className="block text-2xs font-normal text-ink-3">{l.note}</span>}
                  </td>
                  {l.available ? (
                    <>
                      <td className="py-2.5 pl-4 text-right whitespace-nowrap">{fmtValue(l.value, l.kind === 'ratio' ? 'percent' : 'currency')}</td>
                      <td className="py-2.5 pl-4 text-right whitespace-nowrap text-ink-2">{fmtValue(l.previous ?? null, l.kind === 'ratio' ? 'percent' : 'currency')}</td>
                      <td className={cx('py-2.5 pl-4 text-right whitespace-nowrap', (l.change ?? 0) > 0 ? (l.key === 'cost' ? 'text-bad' : 'text-good') : (l.change ?? 0) < 0 ? (l.key === 'cost' ? 'text-good' : 'text-bad') : '')}>
                        {fmtChange(l.change, l.kind === 'ratio' ? 'absolute' : 'relative')}
                      </td>
                    </>
                  ) : <td colSpan={3} className="py-2.5 text-right text-ink-3">Not in dataset</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <ChartCard className="xl:col-span-7" title={`From revenue to ${profitLabel.toLowerCase()}`} subtitle={`Each bar removes the ${costLabel.toLowerCase()} of one segment`}
          loading={loading} rows={data?.waterfall ?? []} height={300}
          empty={data && !data.waterfall.length ? 'Needs both profit and cost (reported or implied).' : undefined}
          columns={[{ key: 'name', label: 'Step', format: 'text' }, { key: 'value', label: 'Amount', format: 'currency' }]}>
          <Waterfall steps={data?.waterfall ?? []} mode="cost" />
        </ChartCard>
      </div>

      <ChartCard title="Financial trend" subtitle="Revenue, cost and profit share one currency axis" loading={loading} rows={trendPivot.rows} height={290}
        columns={[{ key: 'label', label: 'Period', format: 'text' }, ...trendPivot.keys.map((k) => ({ key: k, label: k, format: 'currency' as const }))]}>
        <MultiLine pivot={trendPivot} colorFor={seriesColor} />
      </ChartCard>

      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-7" title={`What moved ${profitLabel.toLowerCase()}`} loading={loading}
          subtitle={data?.bridge ? `${data.meta.comparison_label} to ${data.meta.label}, by ${data.bridge.label.toLowerCase()}` : 'Profit bridge'}
          controls={bridgeDims.length > 1 ? <Select label="Bridge by" value={bridgeDim} onChange={setBridgeDim} options={bridgeDims.map((d) => ({ value: d, label: caps?.filters[d]?.label ?? d }))} /> : undefined}
          rows={data?.bridge?.steps ?? []} height={300}
          empty={data && !data.bridge ? 'A profit bridge needs a comparison period with data and a profit column.' : undefined}
          columns={[{ key: 'name', label: 'Step', format: 'text' }, { key: 'value', label: 'Amount', format: 'currency' }]}>
          <Waterfall steps={data?.bridge?.steps ?? []} mode="signed" />
        </ChartCard>
        <ChartCard className="xl:col-span-5" title={`${costLabel} breakdown`} subtitle={exp ? `By ${exp.label.toLowerCase()}. Click to filter` : undefined}
          controls={expenseDims.length > 1 ? <Select label="Breakdown by" value={activeExpDim ?? ''} onChange={setExpDim} options={expenseDims.map((d) => ({ value: d, label: data!.expense_breakdown[d].label }))} /> : undefined}
          loading={loading} rows={exp?.rows ?? []} height={300} empty={data && !exp ? 'No cost information in this dataset.' : undefined}
          columns={[{ key: 'key', label: 'Segment', format: 'text' }, { key: 'cost', label: costLabel, format: 'currency' }, { key: 'share', label: 'Share', format: 'percent' }, { key: 'cost_ratio', label: 'Cost ÷ revenue', format: 'percent' }]}>
          {exp && <DonutChart rows={exp.rows} valueKey="cost" centerLabel={costLabel} colorFor={(k) => colorFor(activeExpDim!, k)}
            selected={filters[activeExpDim as keyof typeof filters] as string[]} onSelect={(k) => toggleFilter(activeExpDim as never, k)} />}
        </ChartCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-12">
        <ChartCard className="xl:col-span-7" title="Margin by segment" subtitle={marg ? `${profitLabel} margin by ${marg.label.toLowerCase()}` : undefined}
          controls={marginDims.length > 1 ? <Select label="Margin by" value={activeMDim ?? ''} onChange={setMDim} options={marginDims.map((d) => ({ value: d, label: data!.margins[d].label }))} /> : undefined}
          loading={loading} rows={marg?.rows ?? []} height={Math.max(160, (marg?.rows.length ?? 3) * 30 + 16)}
          columns={[{ key: 'key', label: 'Segment', format: 'text' }, { key: 'margin', label: 'Margin', format: 'percent' }, { key: 'revenue', label: 'Revenue', format: 'currency' }, { key: 'margin_change', label: 'Change', format: 'pp' }]}>
          {marg && <BarList rows={marg.rows} valueKey="margin" format="percent" selected={filters[activeMDim as keyof typeof filters] as string[]}
            secondary={{ key: 'revenue', label: 'Revenue', format: 'currency' }} onSelect={(k) => toggleFilter(activeMDim as never, k)} />}
        </ChartCard>
        <Panel className="xl:col-span-5" title="Budget vs actual">
          {data?.budget.available ? (
            <TrendChart data={(data.budget.series ?? []).map((s) => ({ label: s.label, current: s.actual, previous: s.budget }))}
              currentLabel="Actual" previousLabel="Budget" />
          ) : (
            <NotSupported title="Budget data not available" reason={data?.budget.reason ?? 'This dataset has no budget column.'}
              requires={data?.budget.requires} onMap={() => navigate('data')} />
          )}
        </Panel>
      </div>
    </div>
  );
}
