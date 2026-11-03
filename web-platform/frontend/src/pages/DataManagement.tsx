import { Check, CircleCheck, FileSpreadsheet, Sheet, Trash, CloudUpload } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
import { ColumnProfiles, QualityReportView } from '../components/data/QualityReport';
import { PageHeader } from '../components/layout/Shell';
import { Badge, Button, Callout, cx, ErrorNote, Panel, Skeleton } from '../components/ui/primitives';
import { api } from '../lib/api';
import { fmtBytes, fmtDate } from '../lib/format';
import { navigate, useAsync } from '../lib/hooks';
import type { BusinessField, DatasetDetail, SheetAnalysis, UploadResult } from '../lib/types';
import { useApp } from '../state/AppState';

type Step = 'upload' | 'sheet' | 'review' | 'map' | 'done';
const STEPS: { id: Step; label: string }[] = [
  { id: 'upload', label: 'Upload file' }, { id: 'sheet', label: 'Choose sheet' }, { id: 'review', label: 'Preview and quality' },
  { id: 'map', label: 'Map columns' }, { id: 'done', label: 'Process' },
];

export default function DataManagement() {
  const { datasets, dataset } = useApp();
  const [wizard, setWizard] = useState(datasets.length === 0);
  return (
    <div className="space-y-5">
      <PageHeader title="Data management" description="Upload Excel or CSV files, review data quality, map columns to business fields and manage the datasets behind the dashboards."
        actions={!wizard ? <Button variant="primary" icon={<CloudUpload size={16} />} onClick={() => setWizard(true)}>Upload a file</Button> : undefined} />
      {wizard && <UploadWizard onClose={() => setWizard(false)} />}
      <DatasetList />
      {dataset && <ActiveQuality id={dataset.id} updated={dataset.updated_at} />}
    </div>
  );
}

/* ------------------------------------------------------------------ dataset list */
function DatasetList() {
  const { datasets, dataset, setDatasetId, reloadDatasets, toast } = useApp();
  const [busy, setBusy] = useState<number | null>(null);
  if (!datasets.length) return null;
  const remove = async (id: number, name: string) => {
    if (!window.confirm(`Delete “${name}” and all of its rows? This cannot be undone.`)) return;
    setBusy(id);
    try { await api.deleteDataset(id); await reloadDatasets(); toast(`Deleted ${name}`, 'success'); }
    catch (e) { toast((e as Error).message, 'error'); } finally { setBusy(null); }
  };
  return (
    <Panel title="Datasets" subtitle="The active dataset drives every dashboard. Switch it here or from the workspace selector.">
      <div className="overflow-x-auto rounded-lg border border-line">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-xs text-ink-2">
            <tr>{['Dataset', 'Source', 'Rows used', 'Date range', 'Quality', 'Loaded', ''].map((h) => <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>)}</tr>
          </thead>
          <tbody className="tnum">
            {datasets.map((d) => (
              <tr key={d.id} className="border-t border-line">
                <td className="px-3 py-2.5">
                  <span className="font-medium">{d.name}</span>
                  {d.id === dataset?.id && <Badge tone="info" className="ml-2">Active</Badge>}
                  {d.status !== 'ready' && <Badge tone="critical" className="ml-2">{d.status}</Badge>}
                </td>
                <td className="px-3 py-2.5 text-ink-2">{d.source_filename}{d.sheet_name ? `, sheet “${d.sheet_name}”` : ''}</td>
                <td className="px-3 py-2.5">{d.valid_row_count.toLocaleString()} of {d.row_count.toLocaleString()}</td>
                <td className="px-3 py-2.5 text-ink-2">{fmtDate(d.date_min)} to {fmtDate(d.date_max)}</td>
                <td className="px-3 py-2.5">{d.quality_score !== null ? `${d.quality_score.toFixed(0)} (${d.quality_grade})` : '—'}</td>
                <td className="px-3 py-2.5 text-ink-2">{fmtDate(d.created_at)}</td>
                <td className="px-3 py-2.5 text-right whitespace-nowrap">
                  {d.id !== dataset?.id && d.status === 'ready' && <Button size="sm" onClick={() => setDatasetId(d.id)}>Make active</Button>}
                  <Button size="sm" variant="danger" className="ml-2" loading={busy === d.id} icon={<Trash size={13} />} onClick={() => remove(d.id, d.name)} aria-label={`Delete ${d.name}`}>Delete</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function ActiveQuality({ id, updated }: { id: number; updated: string }) {
  const { data, loading } = useAsync(() => api.dataset(id), [id, updated]);
  const p = data?.processing;
  return (
    <Panel title="Data quality report" subtitle={data ? `${data.name}: ${data.source_filename}` : undefined} loading={loading}>
      {!data ? <Skeleton className="h-48 w-full" /> : (
        <div className="space-y-5">
          {p && <ProcessingSummary detail={data} />}
          <QualityReportView report={data.quality} profiles={data.columns} />
        </div>
      )}
    </Panel>
  );
}

function ProcessingSummary({ detail }: { detail: DatasetDetail }) {
  const p = detail.processing;
  const excluded = Object.values(p.excluded_rows ?? {}).reduce((a: number, b) => a + Number(b), 0);
  return (
    <div className="rounded-lg border border-line bg-panel-2 p-4">
      <p className="text-sm font-semibold">How this dataset was processed</p>
      <ul className="mt-2 space-y-1 text-sm text-ink-2">
        {(p.source_notes ?? []).map((n: string) => <li key={n}>{n}.</li>)}
        {(p.steps ?? []).map((s: string) => <li key={s}>{s}.</li>)}
        <li>{detail.valid_row_count.toLocaleString()} of {detail.row_count.toLocaleString()} rows used for analytics{excluded ? `; ${excluded.toLocaleString()} excluded and kept for review in the Data Explorer` : ''}.</li>
        {(p.reconciliation ?? []).length > 0 && <li className="text-good">Post-load reconciliation passed: stored row count, revenue and profit totals match the processed file.</li>}
        {(p.mapping_warnings ?? []).map((w: string) => <li key={w} className="text-warn">{w}</li>)}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ upload wizard */
function Stepper({ step }: { step: Step }) {
  const idx = STEPS.findIndex((s) => s.id === step);
  return (
    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2 text-sm" aria-label="Upload steps">
      {STEPS.map((s, i) => (
        <li key={s.id} className="flex items-center gap-2">
          <span aria-current={i === idx ? 'step' : undefined}
            className={cx('flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold',
              i < idx ? 'bg-accent text-white' : i === idx ? 'bg-navy text-white dark:bg-accent' : 'border border-line-strong text-ink-3')}>
            {i < idx ? <Check size={13} strokeWidth={3} /> : i + 1}
          </span>
          <span className={i === idx ? 'font-medium text-ink' : 'text-ink-3'}>{s.label}</span>
          {i < STEPS.length - 1 && <span className="mx-1 h-px w-6 bg-line-strong" />}
        </li>
      ))}
    </ol>
  );
}

function UploadWizard({ onClose }: { onClose: () => void }) {
  const { reloadDatasets, setDatasetId, toast } = useApp();
  const [step, setStep] = useState<Step>('upload');
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [sheet, setSheet] = useState<string | null>(null);
  const [headerRow, setHeaderRow] = useState<number | null>(null);
  const [analysis, setAnalysis] = useState<SheetAnalysis | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [opts, setOpts] = useState({ revenue_source: 'column', drop_duplicates: true, harmonize_categories: true, trim_whitespace: true });
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [result, setResult] = useState<DatasetDetail | null>(null);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const doUpload = async (file: File) => {
    setBusy(true); setErr(null);
    try {
      const up = await api.upload(file);
      setUpload(up);
      setSheet(up.recommended_sheet ?? up.sheets[0]?.name ?? null);
      setName(file.name.replace(/\.[^.]+$/, ''));
      if (up.file_type === 'csv') { await analyze(up, 'CSV', null); } else setStep('sheet');
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const analyze = async (up: UploadResult, sh: string | null, hdr: number | null) => {
    setBusy(true); setErr(null);
    try {
      const a = await api.analyzeSheet(up.upload_id, up.file_type === 'csv' ? null : sh, hdr);
      setAnalysis(a); setMapping(a.suggestion.mapping); setHeaderRow(a.header_row); setStep('review');
      if (up.file_type !== 'csv' && sh) setName((n) => (n.includes(':') ? n : `${n}: ${sh}`));
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const process = async () => {
    if (!upload || !analysis) return;
    setBusy(true); setErr(null);
    try {
      const ds = await api.createDataset({ upload_id: upload.upload_id, sheet: upload.file_type === 'csv' ? null : sheet, header_row: analysis.header_row,
        name: name.trim() || undefined, mapping, options: opts, set_default: true });
      setResult(ds); setStep('done');
      await reloadDatasets();
      setDatasetId(ds.id);
      toast(`Dataset “${ds.name}” is ready`, 'success');
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };

  return (
    <Panel title="Add a dataset" actions={<Button size="sm" variant="ghost" onClick={onClose}>Close</Button>}>
      <div className="space-y-5">
        <Stepper step={step} />
        {err && <ErrorNote error={err} />}

        {step === 'upload' && (
          <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) void doUpload(f); }}
            className={cx('flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors',
              drag ? 'border-accent bg-accent-soft' : 'border-line-strong bg-panel-2')}>
            <CloudUpload size={34} className="text-accent" />
            <p className="mt-3 text-md font-semibold">Drop an Excel workbook or CSV file here</p>
            <p className="mt-1 text-sm text-ink-2">.xlsx with any number of sheets, or .csv in any common delimiter and encoding.</p>
            <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv,.tsv,.txt" className="sr-only" aria-label="Choose a file"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void doUpload(f); e.target.value = ''; }} />
            <Button variant="primary" className="mt-4" loading={busy} onClick={() => fileRef.current?.click()}>Choose a file</Button>
          </div>
        )}

        {step === 'sheet' && upload && (
          <div className="space-y-4">
            <p className="text-sm text-ink-2"><FileSpreadsheet size={15} className="mr-1 inline" />{upload.filename} ({fmtBytes(upload.size_bytes)}) has {upload.sheets.length} sheets. Pick the one that holds transaction-level data.</p>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {upload.sheets.map((s) => (
                <button key={s.name} onClick={() => setSheet(s.name)} disabled={s.empty}
                  className={cx('rounded-lg border p-3 text-left transition-colors disabled:opacity-40', sheet === s.name ? 'border-accent bg-accent-soft' : 'border-line hover:bg-panel-2')}>
                  <div className="flex items-center justify-between gap-2"><span className="flex items-center gap-1.5 font-medium"><Sheet size={15} />{s.name}</span>
                    {s.name === upload.recommended_sheet && <Badge tone="info">Recommended</Badge>}</div>
                  <p className="mt-1 text-xs text-ink-2">{s.rows?.toLocaleString() ?? '?'} rows × {s.columns ?? '?'} columns</p>
                  {s.header_row > 0 && <p className="mt-0.5 text-xs text-ink-3">Header detected on row {s.header_row + 1}</p>}
                  {(s.columns ?? 0) <= 4 && (s.rows ?? 0) < 50 && <p className="mt-0.5 text-xs text-ink-3">Looks like a lookup table</p>}
                </button>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <Button onClick={() => setStep('upload')}>Back</Button>
              <Button variant="primary" loading={busy} disabled={!sheet} onClick={() => analyze(upload, sheet, null)}>Preview sheet</Button>
            </div>
          </div>
        )}

        {step === 'review' && analysis && upload && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="text-sm text-ink-2">
                <p><b className="text-ink">{analysis.rows.toLocaleString()}</b> rows and <b className="text-ink">{analysis.columns.length}</b> columns read in {analysis.elapsed_ms} ms.</p>
                {analysis.notes.map((n) => <p key={n}>{n}.</p>)}
              </div>
              <label className="flex items-center gap-2 text-sm text-ink-2">Header row
                <input type="number" min={1} max={200} value={(headerRow ?? 0) + 1} onChange={(e) => setHeaderRow(Math.max(0, Number(e.target.value) - 1))}
                  className="h-8 w-16 rounded-md border border-line-strong bg-panel px-2 text-sm" />
                <Button size="sm" loading={busy} onClick={() => analyze(upload, sheet, headerRow)} disabled={headerRow === analysis.header_row}>Re-read</Button>
              </label>
            </div>
            <Preview analysis={analysis} />
            <QualityReportView report={analysis.quality} />
            <div>
              <p className="mb-2 text-sm font-semibold">Detected columns</p>
              <ColumnProfiles profiles={analysis.profiles} />
            </div>
            <div className="flex justify-end gap-2">
              <Button onClick={() => setStep(upload.file_type === 'csv' ? 'upload' : 'sheet')}>Back</Button>
              <Button variant="primary" onClick={() => setStep('map')}>Continue to mapping</Button>
            </div>
          </div>
        )}

        {step === 'map' && analysis && (
          <MappingStep analysis={analysis} mapping={mapping} setMapping={setMapping} opts={opts} setOpts={setOpts} name={name} setName={setName}
            busy={busy} onBack={() => setStep('review')} onProcess={process} />
        )}

        {step === 'done' && result && (
          <div className="space-y-4">
            <Callout tone="info" title={`“${result.name}” is ready and now active`}>
              {result.valid_row_count.toLocaleString()} rows loaded, covering {fmtDate(result.date_min)} to {fmtDate(result.date_max)}. Quality score {result.quality.score.toFixed(0)} ({result.quality.grade}).
            </Callout>
            <ProcessingSummary detail={result} />
            <div className="flex justify-end gap-2">
              <Button onClick={() => { setStep('upload'); setUpload(null); setAnalysis(null); setResult(null); }}>Upload another file</Button>
              <Button variant="primary" icon={<CircleCheck size={16} />} onClick={() => { onClose(); navigate('dashboard'); }}>Open the dashboard</Button>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

function Preview({ analysis }: { analysis: SheetAnalysis }) {
  // Highlight the cells the profiler could not parse, so problems are visible in context.
  const bad = useMemo(() => {
    const m = new Map<string, Set<string>>();
    analysis.profiles.forEach((p) => { if (p.invalid_examples.length) m.set(p.name, new Set(p.invalid_examples.map(String))); });
    return m;
  }, [analysis]);
  return (
    <div>
      <p className="mb-2 text-sm font-semibold">Preview <span className="font-normal text-ink-3">(first {analysis.preview.length} rows; unreadable values are highlighted)</span></p>
      <div className="scroll-thin max-h-[340px] overflow-auto rounded-lg border border-line">
        <table className="text-xs">
          <thead className="sticky top-0 bg-panel-2">
            <tr><th className="border-b border-line px-2 py-1.5 text-left font-medium text-ink-3">Row</th>
              {analysis.columns.map((c) => <th key={c} className="border-b border-line px-2 py-1.5 text-left font-medium whitespace-nowrap text-ink-2">{c}</th>)}</tr>
          </thead>
          <tbody className="tnum">
            {analysis.preview.map((r, i) => (
              <tr key={i} className="border-b border-line last:border-0">
                <td className="px-2 py-1 text-ink-3">{String(r.__row)}</td>
                {analysis.columns.map((c) => {
                  const v = r[c];
                  const isBad = v !== null && bad.get(c)?.has(String(v));
                  return <td key={c} className={cx('px-2 py-1 whitespace-nowrap', isBad && 'bg-bad-soft text-bad', v === null && 'bg-warn-soft/60')}>
                    {v === null ? <span className="text-ink-3">empty</span> : String(v).slice(0, 40)}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MappingStep({ analysis, mapping, setMapping, opts, setOpts, name, setName, busy, onBack, onProcess }: {
  analysis: SheetAnalysis; mapping: Record<string, string>; setMapping: (m: Record<string, string>) => void;
  opts: { revenue_source: string; drop_duplicates: boolean; harmonize_categories: boolean; trim_whitespace: boolean };
  setOpts: (o: { revenue_source: string; drop_duplicates: boolean; harmonize_categories: boolean; trim_whitespace: boolean }) => void;
  name: string; setName: (n: string) => void; busy: boolean; onBack: () => void; onProcess: () => void;
}) {
  const groups = useMemo(() => {
    const g = new Map<string, BusinessField[]>();
    analysis.fields.forEach((f) => g.set(f.group, [...(g.get(f.group) ?? []), f]));
    return [...g.entries()];
  }, [analysis]);
  const prof = (col?: string) => analysis.profiles.find((p) => p.name === col);
  const used = Object.values(mapping);
  const canDerive = !!mapping.unit_price && !!mapping.quantity;
  const missingRequired = !mapping.txn_date || (!mapping.revenue && !canDerive);
  const revCheck = analysis.quality.checks.find((c) => c.id === 'revenue_reconciliation');
  return (
    <div className="space-y-5">
      <p className="text-sm text-ink-2">Each business field drives specific metrics. Suggestions are pre-filled from column names and detected types; check them before processing. Fields left unmapped switch the metrics that need them off instead of estimating them.</p>
      {analysis.suggestion.warnings.map((w) => <Callout key={w} tone="warning">{w}</Callout>)}
      <div className="grid gap-5 xl:grid-cols-2">
        {groups.map(([group, fields]) => (
          <div key={group} className="rounded-lg border border-line">
            <p className="border-b border-line bg-panel-2 px-4 py-2 text-sm font-semibold">{group}</p>
            <ul className="divide-y divide-line">
              {fields.map((f) => {
                const col = mapping[f.key];
                const p = prof(col);
                const typeOk = !p || !f.accepts.length || f.accepts.includes(p.inferred_type);
                const conf = analysis.suggestion.confidence[f.key];
                return (
                  <li key={f.key} className="grid gap-2 px-4 py-2.5 sm:grid-cols-[1fr_200px] sm:items-center">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{f.label}{f.required && <span className="ml-1.5 text-2xs font-normal text-bad">required</span>}
                        {col && conf !== undefined && analysis.suggestion.mapping[f.key] === col && <Badge tone="neutral" className="ml-2">Suggested</Badge>}</p>
                      <p className="text-xs text-ink-3">{f.description}</p>
                      {p && <p className={cx('mt-0.5 truncate text-xs', typeOk ? 'text-ink-2' : 'text-warn')}>
                        {typeOk ? `e.g. ${p.samples.slice(0, 3).map(String).join(', ')}` : `“${col}” looks like ${p.inferred_type}, not ${f.dtype}`}</p>}
                    </div>
                    <select aria-label={`Source column for ${f.label}`} value={col ?? ''}
                      onChange={(e) => { const next = { ...mapping }; if (e.target.value) next[f.key] = e.target.value; else delete next[f.key]; setMapping(next); }}
                      className={cx('h-8 w-full rounded-md border bg-panel px-2 text-sm', col ? 'border-accent/50' : 'border-line-strong text-ink-3')}>
                      <option value="">Not mapped</option>
                      {analysis.columns.map((c) => <option key={c} value={c}>{c}{used.includes(c) && c !== col ? ' (in use)' : ''}</option>)}
                    </select>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-lg border border-line p-4">
          <p className="text-sm font-semibold">Revenue source</p>
          {revCheck && revCheck.status !== 'pass' && <p className="mt-1 text-xs text-warn">{revCheck.detail}</p>}
          <div className="mt-2 space-y-2 text-sm">
            <label className="flex items-start gap-2"><input type="radio" name="rev" checked={opts.revenue_source === 'column'} onChange={() => setOpts({ ...opts, revenue_source: 'column' })} disabled={!mapping.revenue} className="mt-1" />
              <span>Use the mapped revenue column as uploaded{mapping.revenue ? ` (“${mapping.revenue}”)` : ''}</span></label>
            <label className="flex items-start gap-2"><input type="radio" name="rev" checked={opts.revenue_source === 'derived'} onChange={() => setOpts({ ...opts, revenue_source: 'derived' })} disabled={!canDerive} className="mt-1" />
              <span>Derive revenue as unit price × quantity{!canDerive && <span className="text-ink-3"> (map both first)</span>}</span></label>
          </div>
        </div>
        <div className="rounded-lg border border-line p-4">
          <p className="text-sm font-semibold">Cleaning options</p>
          <div className="mt-2 space-y-2 text-sm">
            {([['drop_duplicates', 'Remove exact duplicate rows', `${analysis.quality.summary.duplicate_rows.toLocaleString()} found`],
              ['harmonize_categories', 'Unify spelling variants in text fields', 'e.g. “In-store” and “In-Store”'],
              ['trim_whitespace', 'Trim stray spaces in text', '']] as const).map(([k, label, hint]) => (
              <label key={k} className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={opts[k]} onChange={(e) => setOpts({ ...opts, [k]: e.target.checked })} />
                <span>{label}{hint && <span className="text-ink-3"> ({hint})</span>}</span></label>
            ))}
            <p className="text-xs text-ink-3">Missing or unreadable dates and revenue are never filled in. Those rows are kept, flagged, and left out of the analytics.</p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink-2">Dataset name
          <input value={name} onChange={(e) => setName(e.target.value)} className="h-9 w-80 max-w-full rounded-md border border-line-strong bg-panel px-2.5 text-sm text-ink" />
        </label>
        <div className="flex gap-2">
          <Button onClick={onBack}>Back</Button>
          <Button variant="primary" loading={busy} disabled={missingRequired} onClick={onProcess}>Process dataset</Button>
        </div>
      </div>
      {missingRequired && <p className="text-right text-xs text-bad">Map a transaction date and a revenue column (or unit price and quantity) to continue.</p>}
    </div>
  );
}
