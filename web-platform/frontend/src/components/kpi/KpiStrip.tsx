import { TriangleAlert, ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import { fmtChange, fmtValue } from '../../lib/format';
import type { Kpi } from '../../lib/types';
import { useApp } from '../../state/AppState';
import { Sparkline } from '../charts/charts';
import { cx, Skeleton } from '../ui/primitives';

export function KpiCard({ kpi, comparisonLabel, attention }: { kpi: Kpi; comparisonLabel?: string; attention?: boolean }) {
  const { chart, prefs } = useApp();
  if (!kpi.available) {
    return (
      <div className="flex min-h-[148px] flex-col px-5 py-4">
        <p className="text-xs font-medium text-ink-2">{kpi.label}</p>
        <p className="mt-2 text-lg font-semibold text-ink-3">Not available</p>
        <p className="mt-1 text-xs text-ink-3">{kpi.reason}</p>
      </div>
    );
  }
  const Icon = kpi.direction === 'up' ? ArrowUpRight : kpi.direction === 'down' ? ArrowDownRight : Minus;
  const tone = kpi.sentiment === 'positive' ? 'text-good' : kpi.sentiment === 'negative' ? 'text-bad' : 'text-ink-2';
  return (
    <div className="flex min-h-[148px] flex-col px-5 py-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium text-ink-2">{kpi.label}</p>
        {attention && (
          <span className="inline-flex items-center gap-1 rounded-full bg-bad-soft px-1.5 py-0.5 text-2xs font-medium text-bad" title="Moved adversely beyond the attention threshold">
            <TriangleAlert size={11} /> Attention
          </span>
        )}
      </div>
      <p className="mt-1.5 text-[28px] font-semibold leading-none tracking-tight" title={fmtValue(kpi.value, kpi.format, false)}>
        {fmtValue(kpi.value, kpi.format, prefs.compactNumbers)}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
        {kpi.change !== null && kpi.change !== undefined ? (
          <>
            <span className={cx('inline-flex items-center gap-0.5 font-semibold', tone)}>
              <Icon size={14} strokeWidth={2.4} />{fmtChange(kpi.change, kpi.change_type)}
            </span>
            <span className="text-ink-3">vs {comparisonLabel || 'previous'} ({fmtValue(kpi.previous, kpi.format)})</span>
          </>
        ) : (
          <span className="text-ink-3">{kpi.key === 'growth_rate' && comparisonLabel ? `Growth over ${comparisonLabel}; no earlier period to compare` : comparisonLabel ? `No ${comparisonLabel} data to compare` : 'No comparison period selected'}</span>
        )}
      </div>
      <div className="mt-auto pt-2">
        {kpi.sparkline && kpi.sparkline.length > 2 ? <Sparkline data={kpi.sparkline} color={chart.series[0]} /> : null}
        {kpi.note && <p className="mt-1 truncate text-2xs text-ink-3" title={kpi.note}>{kpi.note}</p>}
      </div>
    </div>
  );
}

export function KpiStrip({ kpis, comparisonLabel, attention = [], loading, columns = 4 }: {
  kpis?: Kpi[]; comparisonLabel?: string; attention?: string[]; loading?: boolean; columns?: 4 | 3;
}) {
  return (
    <section aria-label="Key performance indicators"
      className={cx('grid overflow-hidden rounded-xl border border-line bg-panel sm:grid-cols-2',
        columns === 4 ? 'xl:grid-cols-4' : 'xl:grid-cols-3', loading && 'loading-bar')}>
      {!kpis
        ? Array.from({ length: columns === 4 ? 8 : 6 }).map((_, i) => (
          <div key={i} className="border-b border-r border-line px-5 py-4"><Skeleton className="h-3 w-24" /><Skeleton className="mt-3 h-7 w-32" /><Skeleton className="mt-3 h-8 w-full" /></div>
        ))
        : kpis.map((k) => (
          <div key={k.key} className="-mb-px -mr-px border-b border-r border-line">
            <KpiCard kpi={k} comparisonLabel={comparisonLabel} attention={attention.includes(k.key)} />
          </div>
        ))}
    </section>
  );
}
