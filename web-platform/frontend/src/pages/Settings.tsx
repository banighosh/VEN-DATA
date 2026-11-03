import { Laptop, Moon, Sun } from 'lucide-react';
import { PageHeader } from '../components/layout/Shell';
import { Badge, Button, cx, Panel, Segmented } from '../components/ui/primitives';
import { api } from '../lib/api';
import { fmtDate } from '../lib/format';
import { useAsync } from '../lib/hooks';
import type { Comparison } from '../lib/types';
import { useApp } from '../state/AppState';

export default function Settings() {
  const { prefs, setPrefs, dataset, toast } = useApp();
  const { data: info } = useAsync(() => api.systemInfo(), []);
  const { data: health, reload } = useAsync(() => api.health(), []);
  const { data: presets, reload: reloadPresets } = useAsync(() => api.presets(), []);
  return (
    <div className="max-w-4xl space-y-5">
      <PageHeader title="Settings" description="Display preferences are stored in this browser. Saved views are stored on the server for everyone using this workspace." />
      <Panel title="Appearance">
        <div className="grid gap-3 sm:grid-cols-3">
          {([['light', 'Light', Sun], ['dark', 'Dark', Moon], ['system', 'Match system', Laptop]] as const).map(([v, l, Icon]) => (
            <button key={v} onClick={() => setPrefs({ themePref: v })} aria-pressed={prefs.themePref === v}
              className={cx('flex items-center gap-3 rounded-lg border p-4 text-left', prefs.themePref === v ? 'border-accent bg-accent-soft' : 'border-line hover:bg-panel-2')}>
              <Icon size={20} /> <span className="font-medium">{l}</span>
            </button>
          ))}
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={prefs.compactNumbers} onChange={(e) => setPrefs({ compactNumbers: e.target.checked })} />
          Show KPI values in compact form ($717.82M instead of $717,821,450)</label>
      </Panel>
      <Panel title="Default analysis period">
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>When a dataset opens, show</span>
            <Segmented size="md" label="Default range" value={prefs.defaultRange} onChange={(v) => setPrefs({ defaultRange: v })}
              options={[{ value: 'latest_year', label: 'Latest full year' }, { value: 'all', label: 'All time' }]} />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>Compare KPIs with</span>
            <Segmented size="md" label="Default comparison" value={prefs.comparison} onChange={(v) => setPrefs({ comparison: v as Comparison })}
              options={[{ value: 'previous_period', label: 'Previous period' }, { value: 'previous_year', label: 'Same period last year' }, { value: 'none', label: 'Nothing' }]} />
          </div>
          <p className="text-xs text-ink-3">Applies the next time a dataset loads or when you press Reset in the filter bar.</p>
        </div>
      </Panel>
      <Panel title="Saved views" subtitle="Named filter combinations. Apply them from Saved views in the filter bar.">
        <ul className="divide-y divide-line rounded-lg border border-line">
          {(presets ?? []).map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
              <span><span className="font-medium">{p.name}</span><span className="ml-2 text-xs text-ink-3">saved {fmtDate(p.created_at)}</span></span>
              <Button size="sm" variant="danger" onClick={async () => { await api.deletePreset(p.id); reloadPresets(); toast(`Deleted ${p.name}`, 'success'); }}>Delete</Button>
            </li>
          ))}
          {(presets ?? []).length === 0 && <li className="px-4 py-3 text-sm text-ink-3">No saved views yet.</li>}
        </ul>
      </Panel>
      <Panel title="Platform status" actions={<Button size="sm" variant="ghost" onClick={reload}>Refresh</Button>}>
        <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          <div><dt className="text-ink-3">API</dt><dd>{health ? <Badge tone="good">Online</Badge> : <Badge tone="warning">Checking</Badge>} {info && `${info.name} ${info.version}`}</dd></div>
          <div><dt className="text-ink-3">Database</dt><dd className="capitalize">{health?.database ?? '—'}</dd></div>
          <div><dt className="text-ink-3">Environment</dt><dd>{info?.environment ?? '—'}</dd></div>
          <div><dt className="text-ink-3">Upload limit</dt><dd>{info ? `${info.max_upload_mb} MB` : '—'}</dd></div>
          <div className="sm:col-span-2"><dt className="text-ink-3">AI interpretation of insights</dt>
            <dd>{info?.ai_insights.enabled ? <>Enabled with {info.ai_insights.model}</> : 'Off. Interpretations are rule-based. Set ANTHROPIC_API_KEY on the API service to enable.'}</dd></div>
          <div className="sm:col-span-2"><dt className="text-ink-3">Active dataset</dt><dd>{dataset ? `${dataset.name} (${dataset.valid_row_count.toLocaleString()} rows)` : 'None'}</dd></div>
        </dl>
      </Panel>
    </div>
  );
}
