import { Sparkles } from 'lucide-react';
import { useMemo, useState } from 'react';
import { InsightCard } from '../components/insights/InsightCard';
import { PageHeader, ScopeNote } from '../components/layout/Shell';
import { Callout, ErrorNote, Segmented, Skeleton } from '../components/ui/primitives';
import type { Insight, ScopeMeta } from '../lib/types';
import { useModule } from '../lib/useModule';

interface InsData { meta: ScopeMeta; insights: Insight[]; ai: { enabled: boolean; configured: boolean; model: string; applied?: boolean; error?: string } }

export default function Insights() {
  const [useAi, setUseAi] = useState(true);
  const { data, loading, error, reload } = useModule<InsData>('insights', { use_ai: useAi, limit: 20 });
  const [sev, setSev] = useState<'all' | Insight['severity']>('all');
  const list = useMemo(() => (data?.insights ?? []).filter((i) => sev === 'all' || i.severity === sev), [data, sev]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    (data?.insights ?? []).forEach((i) => { c[i.severity] = (c[i.severity] ?? 0) + 1; });
    return c;
  }, [data]);
  return (
    <div className="space-y-5">
      <PageHeader title="AI-assisted insights" meta={<ScopeNote meta={data?.meta} />}
        description="Each insight states what was measured, the metrics behind it, what it implies and what to do next. Statistics and interpretation are kept visibly separate."
        actions={data?.ai.enabled ? (
          <Segmented value={useAi ? 'ai' : 'rule'} onChange={(v) => setUseAi(v === 'ai')} label="Interpretation source" size="md"
            options={[{ value: 'ai', label: 'AI interpretation' }, { value: 'rule', label: 'Rules only' }]} />
        ) : undefined} />
      {error && <ErrorNote error={error} onRetry={reload} />}
      {data && !data.ai.enabled && (
        <Callout tone="info" title="Interpretations are rule-based">
          Every observation and metric is computed from your filtered data. The implication and recommendation come from transparent rules.
          To add AI-written interpretations, set ANTHROPIC_API_KEY on the API service; the model only rewrites interpretation, never the measured facts,
          and is instructed not to assert causes the data cannot show.
        </Callout>
      )}
      {data?.ai.error && <Callout tone="warning">{data.ai.error}</Callout>}
      {data?.ai.applied && (
        <p className="inline-flex items-center gap-1.5 text-xs text-ink-3"><Sparkles size={13} /> Interpretations written by {data.ai.model}. Observations and metrics are unchanged statistical output.</p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Segmented value={sev} onChange={setSev} label="Severity" size="md" options={[
          { value: 'all', label: `All (${data?.insights.length ?? 0})` },
          { value: 'critical', label: `Critical (${counts.critical ?? 0})` }, { value: 'warning', label: `Watch (${counts.warning ?? 0})` },
          { value: 'positive', label: `Positive (${counts.positive ?? 0})` }, { value: 'info', label: `Context (${counts.info ?? 0})` }]} />
      </div>
      <div className={loading ? 'loading-bar space-y-3' : 'space-y-3'}>
        {!data && loading && Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-48 w-full" />)}
        {list.map((i) => <InsightCard key={i.id} insight={i} />)}
        {data && !list.length && <p className="text-sm text-ink-3">No insights in this category for the current filters.</p>}
      </div>
    </div>
  );
}
