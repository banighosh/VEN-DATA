import { OctagonAlert, TriangleAlert, CircleCheck, Info, Sparkles, Ruler, ChevronRight } from 'lucide-react';
import { fmtValue } from '../../lib/format';
import { navigate, type Page } from '../../lib/hooks';
import type { Dimension, Insight } from '../../lib/types';
import { useApp } from '../../state/AppState';
import { cx } from '../ui/primitives';

const SEVERITY = {
  critical: { icon: OctagonAlert, label: 'Critical', bar: 'bg-bad', text: 'text-bad' },
  warning: { icon: TriangleAlert, label: 'Watch', bar: 'bg-warn', text: 'text-warn' },
  positive: { icon: CircleCheck, label: 'Positive', bar: 'bg-good', text: 'text-good' },
  info: { icon: Info, label: 'Context', bar: 'bg-accent', text: 'text-accent-ink' },
} as const;

const PAGE_MAP: Record<string, Page> = {
  performance: 'performance', products: 'products', regional: 'regional', customers: 'customers', operations: 'operations',
  executive: 'executive', 'data-management': 'data', financial: 'financial',
};

/**
 * Insight layout makes the epistemic split visible: the left side is measured
 * (statistics computed from the filtered data); the hatched right side is
 * interpretation, labelled with where it came from (rules or AI).
 */
export function InsightCard({ insight, compact }: { insight: Insight; compact?: boolean }) {
  const { setFilters } = useApp();
  const sev = SEVERITY[insight.severity];
  const SevIcon = sev.icon;
  const ai = insight.interpretation_source === 'ai';
  const drill = () => {
    if (insight.drill?.filter) {
      setFilters((f) => {
        const next = { ...f };
        for (const [k, v] of Object.entries(insight.drill!.filter!)) next[k as Dimension] = v as string[];
        return next;
      });
    }
    const page = insight.drill?.page ? PAGE_MAP[insight.drill.page] : undefined;
    if (page) navigate(page);
  };
  return (
    <article className="relative overflow-hidden rounded-xl border border-line bg-panel">
      <span className={cx('absolute inset-y-0 left-0 w-[3px]', sev.bar)} aria-hidden="true" />
      <div className={cx('grid', !compact && 'lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]')}>
        <div className="py-4 pl-5 pr-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className={cx('inline-flex items-center gap-1 text-xs font-semibold', sev.text)}><SevIcon size={14} />{sev.label}</span>
            <span className="text-2xs text-ink-3">Confidence: {insight.confidence}</span>
          </div>
          <h3 className="mt-1.5 text-[15px] font-semibold leading-snug">{insight.title}</h3>
          <p className="mt-3 flex items-center gap-1.5 text-2xs font-medium text-ink-3"><Ruler size={12} /> Observation (measured)</p>
          <p className="mt-1 text-sm text-ink-2">{insight.observation}</p>
          {insight.metrics.length > 0 && (
            <>
              <p className="mt-3 text-2xs font-medium text-ink-3">Supporting metrics</p>
              <dl className="mt-1.5 flex flex-wrap gap-2">
                {insight.metrics.slice(0, compact ? 3 : 5).map((m) => (
                  <div key={m.label} className="rounded-md border border-line bg-panel-2 px-2.5 py-1.5">
                    <dt className="max-w-[180px] truncate text-2xs text-ink-3" title={m.label}>{m.label}</dt>
                    <dd className="tnum text-sm font-semibold">{fmtValue(m.value, m.format)}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}
        </div>
        <div className={cx('interp-hatch border-line px-5 py-4', compact ? 'border-t' : 'border-t lg:border-l lg:border-t-0')}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-2xs font-medium text-ink-3">Interpretation</p>
            <span className={cx('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-2xs font-medium',
              ai ? 'border-accent/40 bg-accent-soft text-accent-ink' : 'border-line-strong bg-panel text-ink-2')}
              title={ai ? 'Written by an AI model from the measured facts on the left' : 'Produced by transparent, deterministic rules'}>
              {ai ? <Sparkles size={11} /> : null}{ai ? 'AI-generated' : 'Rule-based'}
            </span>
          </div>
          <p className="mt-2 text-2xs font-medium text-ink-3">Business implication</p>
          <p className="mt-0.5 text-sm text-ink">{insight.implication}</p>
          <p className="mt-3 text-2xs font-medium text-ink-3">Recommended action</p>
          <p className="mt-0.5 text-sm text-ink">{insight.recommendation}</p>
          {insight.drill?.page && (
            <button onClick={drill} className="mt-3 inline-flex items-center gap-0.5 text-xs font-medium text-accent-ink hover:underline">
              Explore the data <ChevronRight size={13} />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

export function InsightList({ insights, compact, limit }: { insights?: Insight[]; compact?: boolean; limit?: number }) {
  if (!insights) return null;
  const items = limit ? insights.slice(0, limit) : insights;
  if (!items.length) return <p className="text-sm text-ink-3">No insights for the current selection.</p>;
  return <div className={cx('grid gap-3', compact && 'xl:grid-cols-2')}>{items.map((i) => <InsightCard key={i.id} insight={i} compact={compact} />)}</div>;
}
