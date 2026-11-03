import { CircleCheck, Info, OctagonAlert, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import type { ColumnProfile, QualityReport as QR } from '../../lib/types';
import { Badge, cx, Segmented } from '../ui/primitives';
import { DataTable } from './DataTable';

const SEV = {
  critical: { icon: OctagonAlert, cls: 'text-bad', label: 'Critical' },
  warning: { icon: TriangleAlert, cls: 'text-warn', label: 'Warning' },
  info: { icon: Info, cls: 'text-accent', label: 'Info' },
} as const;

const TYPE_LABEL: Record<string, string> = {
  date: 'Date', number: 'Number', integer: 'Whole number', currency: 'Currency', percent: 'Percentage', text: 'Text',
  category: 'Category', id: 'Identifier', boolean: 'Yes / no', empty: 'Empty',
};

export function QualityReportView({ report, profiles }: { report: QR; profiles?: ColumnProfile[] }) {
  const [tab, setTab] = useState<'issues' | 'checks' | 'columns'>('issues');
  const dims = [
    ['Completeness', report.dimensions.completeness, 'Share of cells with a value'],
    ['Uniqueness', report.dimensions.uniqueness, 'Share of rows that are not exact duplicates'],
    ['Validity', report.dimensions.validity, 'Share of values that parse as their column type'],
    ['Consistency', report.dimensions.consistency, 'Average pass rate of cross-field checks'],
  ] as const;
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-[220px_1fr]">
        <div className="rounded-lg border border-line bg-panel-2 p-4">
          <p className="text-xs text-ink-2">Quality score</p>
          <p className="mt-1 text-[44px] font-semibold leading-none tracking-tight">{report.score.toFixed(0)}<span className="text-lg text-ink-3">/100</span></p>
          <p className="mt-2 text-sm text-ink-2">Grade {report.grade}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Badge tone={report.summary.critical ? 'critical' : 'good'}>{report.summary.critical} critical</Badge>
            <Badge tone={report.summary.warnings ? 'warning' : 'good'}>{report.summary.warnings} warnings</Badge>
          </div>
          {report.summary.sampled && <p className="mt-2 text-2xs text-ink-3">Profiled on a sample of the first rows.</p>}
        </div>
        <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
          {dims.map(([label, v, hint]) => (
            <div key={label}>
              <div className="flex items-baseline justify-between text-sm"><span className="font-medium">{label}</span><span className="tnum">{v.toFixed(1)}%</span></div>
              <div className="mt-1.5 h-2 rounded-full bg-accent-soft">
                <div className={cx('h-2 rounded-full', v >= 95 ? 'bg-accent' : v >= 80 ? 'bg-warn' : 'bg-bad')} style={{ width: `${Math.max(2, v)}%` }} />
              </div>
              <p className="mt-1 text-2xs text-ink-3">{hint}</p>
            </div>
          ))}
          <div className="col-span-full grid grid-cols-2 gap-3 text-sm text-ink-2 sm:grid-cols-4">
            <span><b className="tnum text-ink">{report.summary.rows.toLocaleString()}</b> rows</span>
            <span><b className="tnum text-ink">{report.summary.missing_cells.toLocaleString()}</b> missing cells</span>
            <span><b className="tnum text-ink">{report.summary.duplicate_rows.toLocaleString()}</b> duplicate rows</span>
            <span><b className="tnum text-ink">{report.summary.invalid_values.toLocaleString()}</b> invalid values</span>
          </div>
        </div>
      </div>
      <Segmented value={tab} onChange={setTab} label="Report section" size="md" options={[
        { value: 'issues', label: `Issues (${report.issues.length})` }, { value: 'checks', label: `Consistency checks (${report.checks.length})` },
        ...(profiles ? [{ value: 'columns' as const, label: `Columns (${profiles.length})` }] : [])]} />
      {tab === 'issues' && (
        report.issues.length === 0
          ? <p className="flex items-center gap-2 text-sm text-good"><CircleCheck size={16} /> No issues found.</p>
          : <ul className="divide-y divide-line rounded-lg border border-line">
            {report.issues.map((i, n) => {
              const S = SEV[i.severity];
              return (
                <li key={n} className="flex gap-3 px-4 py-3">
                  <S.icon size={17} className={cx('mt-0.5 shrink-0', S.cls)} aria-label={S.label} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-ink">{i.message}</p>
                    <p className="mt-0.5 text-xs text-ink-3">
                      {S.label}{i.column ? `, column “${i.column}”` : ''}{i.count ? `, ${i.count.toLocaleString()} affected` : ''}
                      {i.examples.length > 0 && <>. Examples: {i.examples.slice(0, 3).map((e) => `“${String(e)}”`).join(', ')}</>}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
      )}
      {tab === 'checks' && (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {report.checks.map((c) => (
            <li key={c.id} className="flex gap-3 px-4 py-3">
              {c.status === 'pass' ? <CircleCheck size={17} className="mt-0.5 shrink-0 text-good" /> : c.status === 'fail' ? <OctagonAlert size={17} className="mt-0.5 shrink-0 text-bad" />
                : c.status === 'warn' ? <TriangleAlert size={17} className="mt-0.5 shrink-0 text-warn" /> : <Info size={17} className="mt-0.5 shrink-0 text-accent" />}
              <div><p className="text-sm font-medium">{c.name} <span className="font-normal text-ink-3">({c.status === 'pass' ? 'passed' : `${c.affected_pct}% of rows`})</span></p>
                <p className="mt-0.5 text-sm text-ink-2">{c.detail}</p></div>
            </li>
          ))}
          {report.checks.length === 0 && <li className="px-4 py-3 text-sm text-ink-3">Map date and revenue columns to run consistency checks.</li>}
        </ul>
      )}
      {tab === 'columns' && profiles && <ColumnProfiles profiles={profiles} />}
    </div>
  );
}

export function ColumnProfiles({ profiles }: { profiles: ColumnProfile[] }) {
  return (
    <DataTable rows={profiles as unknown as Record<string, unknown>[]} dense maxHeight={460}
      columns={[
        { key: 'name', label: 'Column', format: 'text' },
        { key: 'inferred_type', label: 'Detected type', format: 'text', render: (r) => TYPE_LABEL[String(r.inferred_type)] ?? String(r.inferred_type) },
        { key: 'missing', label: 'Missing', format: 'number', render: (r) => `${Number(r.missing).toLocaleString()} (${r.missing_pct}%)` },
        { key: 'unique', label: 'Distinct', format: 'number' },
        { key: 'invalid', label: 'Invalid', format: 'number', render: (r) => (Number(r.invalid) ? <span className="text-bad">{Number(r.invalid).toLocaleString()}</span> : '0') },
        { key: 'notes', label: 'Formatting', format: 'text', render: (r) => {
          const p = r as unknown as ColumnProfile;
          const notes = [p.case_variants.length ? `${p.case_variants.length} spelling variant(s): ${p.case_variants[0].join(' / ')}` : null,
            p.whitespace_issues ? `${p.whitespace_issues} spacing issue(s)` : null, p.mixed_types ? 'mixed numbers and text' : null,
            p.outliers ? `${p.outliers} extreme outlier(s)` : null].filter(Boolean);
          return notes.length ? <span className="text-warn">{notes.join('; ')}</span> : <span className="text-ink-3">—</span>;
        } },
        { key: 'samples', label: 'Sample values', format: 'text', render: (r) => <span className="text-ink-2">{(r.samples as unknown[]).slice(0, 3).map(String).join(', ')}</span> },
      ]} />
  );
}
