import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Columns3, FileDown, FileSpreadsheet, Search } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { PageHeader } from '../components/layout/Shell';
import { Badge, Button, cx, Drawer, ErrorNote, Select } from '../components/ui/primitives';
import { api, compactFilters, downloadPost } from '../lib/api';
import { fmtDate, fmtValue } from '../lib/format';
import { readStore, useAsync, useClickOutside, useDebounced, writeStore } from '../lib/hooks';
import { useApp } from '../state/AppState';

interface Col { key: string; label: string; type: 'text' | 'number' | 'date'; format?: 'currency' | 'percent' | null; source: string | null; derived?: boolean }
interface Page { total: number; page: number; page_size: number; columns: Col[]; visible: string[]; rows: Record<string, unknown>[] }
interface Detail { id: number; row_number: number; is_valid: boolean; issues: string[]; fields: (Col & { value: unknown })[]; raw: Record<string, unknown> }

const ISSUE_TEXT: Record<string, string> = {
  revenue_mismatch: 'Revenue ≠ unit price × quantity', revenue_outlier: 'Revenue is an extreme outlier', missing_date: 'Missing date',
  invalid_date: 'Unreadable date', missing_revenue: 'Missing revenue', invalid_revenue: 'Unreadable revenue', negative_revenue: 'Negative revenue',
};

function formatCell(v: unknown, c: Col) {
  if (v === null || v === undefined || v === '') return <span className="text-ink-3">—</span>;
  if (c.key === 'issues') return (String(v).split(',').map((i) => <Badge key={i} tone="warning" className="mr-1">{ISSUE_TEXT[i] ?? i}</Badge>));
  if (c.type === 'date') return fmtDate(String(v));
  if (c.type === 'number') return fmtValue(Number(v), c.format === 'currency' ? 'currency' : c.format === 'percent' ? 'percent' : 'number', false);
  return String(v);
}

export default function Explorer() {
  const { dataset, filters, toast } = useApp();
  const [search, setSearch] = useState('');
  const dSearch = useDebounced(search, 300);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sort, setSort] = useState<{ by: string; dir: 'asc' | 'desc' }>({ by: 'row_number', dir: 'asc' });
  const [includeExcluded, setIncludeExcluded] = useState(false);
  const [issuesOnly, setIssuesOnly] = useState(false);
  const storeKey = `meridian.explorer.cols.${dataset?.id}`;
  const [hidden, setHidden] = useState<string[]>(() => readStore<string[]>(storeKey, []));
  const [colsOpen, setColsOpen] = useState(false);
  const colsRef = useRef<HTMLDivElement>(null);
  useClickOutside(colsRef, () => setColsOpen(false), colsOpen);
  const [detailId, setDetailId] = useState<number | null>(null);
  const fkey = JSON.stringify(compactFilters(filters));
  useEffect(() => { setPage(1); }, [fkey, dSearch, includeExcluded, issuesOnly, pageSize]);
  useEffect(() => { writeStore(storeKey, hidden); }, [hidden, storeKey]);

  const body = { filters: compactFilters(filters), page, page_size: pageSize, sort_by: sort.by, sort_dir: sort.dir, search: dSearch || null,
    include_excluded: includeExcluded, issues_only: issuesOnly };
  const { data, loading, error, reload } = useAsync((s) => api.records<Page>(dataset!.id, body, s),
    [dataset?.id, JSON.stringify(body)], !!dataset);
  const { data: detail } = useAsync(() => api.record<Detail>(dataset!.id, detailId!), [detailId], detailId !== null);
  const cols = useMemo(() => (data?.columns ?? []).filter((c) => !hidden.includes(c.key)), [data, hidden]);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const exportAs = async (format: 'csv' | 'xlsx') => {
    try {
      await downloadPost(`/api/datasets/${dataset!.id}/export`, { filters: compactFilters(filters), format, search: dSearch || null,
        include_excluded: includeExcluded, columns: cols.map((c) => c.key), sort_by: sort.by, sort_dir: sort.dir }, `data.${format}`);
      toast(`Exported ${data?.total.toLocaleString()} rows`, 'success');
    } catch (e) { toast((e as Error).message, 'error'); }
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Data explorer" description="Every row behind the dashboards, with the global filters applied. Search, sort, choose columns, export, or open a row to see its original values and any data issues." />
      {error && <ErrorNote error={error} onRetry={reload} />}
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex h-9 w-full max-w-sm items-center gap-2 rounded-md border border-line-strong bg-panel px-2.5 focus-within:border-accent">
          <Search size={15} className="text-ink-3" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search text fields or source row number"
            className="w-full bg-transparent text-sm outline-none placeholder:text-ink-3" aria-label="Search records" />
        </label>
        <div className="relative" ref={colsRef}>
          <Button icon={<Columns3 size={15} />} onClick={() => setColsOpen((o) => !o)} aria-expanded={colsOpen}>Columns ({cols.length})</Button>
          {colsOpen && (
            <div className="absolute left-0 top-11 z-30 w-64 rounded-lg border border-line bg-panel p-2 shadow-pop">
              <div className="scroll-thin max-h-72 overflow-y-auto">
                {(data?.columns ?? []).map((c) => (
                  <label key={c.key} className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-panel-2">
                    <input type="checkbox" checked={!hidden.includes(c.key)} onChange={() => setHidden((h) => (h.includes(c.key) ? h.filter((x) => x !== c.key) : [...h, c.key]))} />
                    <span className="flex-1">{c.label}</span>
                    {c.source && <span className="truncate text-2xs text-ink-3">{c.source}</span>}
                  </label>
                ))}
              </div>
              <div className="mt-1 flex justify-between border-t border-line pt-2">
                <Button size="sm" variant="ghost" onClick={() => setHidden([])}>Show all</Button>
                <Button size="sm" variant="primary" onClick={() => setColsOpen(false)}>Done</Button>
              </div>
            </div>
          )}
        </div>
        <label className="inline-flex items-center gap-2 text-sm text-ink-2"><input type="checkbox" checked={includeExcluded} onChange={(e) => setIncludeExcluded(e.target.checked)} /> Include excluded rows</label>
        <label className="inline-flex items-center gap-2 text-sm text-ink-2"><input type="checkbox" checked={issuesOnly} onChange={(e) => setIssuesOnly(e.target.checked)} /> Only rows with issues</label>
        <div className="ml-auto flex gap-2">
          <Button icon={<FileDown size={15} />} onClick={() => exportAs('csv')}>CSV</Button>
          <Button icon={<FileSpreadsheet size={15} />} onClick={() => exportAs('xlsx')}>Excel</Button>
        </div>
      </div>

      <div className={cx('scroll-thin overflow-auto rounded-xl border border-line bg-panel', loading && 'loading-bar')} style={{ maxHeight: 'calc(100vh - 290px)', minHeight: 320 }}>
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 z-10 bg-panel-2">
            <tr>
              {cols.map((c) => {
                const active = sort.by === c.key;
                const right = c.type === 'number';
                return (
                  <th key={c.key} scope="col" aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                    className={cx('border-b border-line px-3 py-2 text-xs font-medium text-ink-2 whitespace-nowrap', right ? 'text-right' : 'text-left')}>
                    <button onClick={() => setSort((s) => ({ by: c.key, dir: s.by === c.key && s.dir === 'asc' ? 'desc' : 'asc' }))}
                      className={cx('inline-flex items-center gap-1 hover:text-ink', right && 'flex-row-reverse')} title={c.source ? `Source column: ${c.source}${c.derived ? ' (derived)' : ''}` : undefined}>
                      {c.label}{c.derived && <span className="text-ink-3">*</span>}
                      {active ? (sort.dir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />) : <span className="w-3" />}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="tnum">
            {(data?.rows ?? []).map((r) => (
              <tr key={String(r.id)} onClick={() => setDetailId(Number(r.id))}
                className={cx('cursor-pointer border-b border-line hover:bg-panel-2', r.is_valid === false && 'bg-bad-soft/50')}>
                {cols.map((c) => (
                  <td key={c.key} className={cx('px-3 py-2 whitespace-nowrap', c.type === 'number' ? 'text-right' : 'text-left')}>{formatCell(r[c.key], c)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.rows.length === 0 && <p className="py-12 text-center text-sm text-ink-3">No rows match the current filters and search.</p>}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-ink-2">
        <span>{data ? `${((data.page - 1) * data.page_size + (data.rows.length ? 1 : 0)).toLocaleString()}–${((data.page - 1) * data.page_size + data.rows.length).toLocaleString()} of ${data.total.toLocaleString()} rows` : '…'}
          {cols.some((c) => c.derived) && <span className="ml-3 text-ink-3">* derived field</span>}</span>
        <div className="flex items-center gap-2">
          <Select label="Rows per page" value={String(pageSize)} onChange={(v) => setPageSize(Number(v))} options={[25, 50, 100, 250].map((n) => ({ value: String(n), label: `${n} per page` }))} />
          <Button size="sm" icon={<ChevronLeft size={15} />} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="tnum">Page {page} of {pages}</span>
          <Button size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next <ChevronRight size={15} /></Button>
        </div>
      </div>

      <Drawer open={detailId !== null} onClose={() => setDetailId(null)} title={detail ? `Source row ${detail.row_number}` : 'Record'}>
        {detail && (
          <div className="space-y-5">
            <div className="flex flex-wrap gap-2">
              <Badge tone={detail.is_valid ? 'good' : 'critical'}>{detail.is_valid ? 'Included in analytics' : 'Excluded from analytics'}</Badge>
              {detail.issues.map((i) => <Badge key={i} tone="warning">{ISSUE_TEXT[i] ?? i}</Badge>)}
            </div>
            <section>
              <h3 className="mb-2 text-sm font-semibold">Mapped business fields</h3>
              <dl className="divide-y divide-line rounded-lg border border-line">
                {detail.fields.map((f) => (
                  <div key={f.key} className="grid grid-cols-[1fr_1fr] gap-3 px-3 py-2 text-sm">
                    <dt className="text-ink-2">{f.label}{f.source && <span className="block text-2xs text-ink-3">{f.derived ? 'Derived' : `From “${f.source}”`}</span>}</dt>
                    <dd className="tnum text-right">{formatCell(f.value, f)}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section>
              <h3 className="mb-2 text-sm font-semibold">Original values as uploaded</h3>
              <dl className="divide-y divide-line rounded-lg border border-line">
                {Object.entries(detail.raw).map(([k, v]) => (
                  <div key={k} className="grid grid-cols-[1fr_1fr] gap-3 px-3 py-2 text-sm">
                    <dt className="text-ink-2">{k}</dt><dd className="tnum break-words text-right">{v === null ? <span className="text-ink-3">empty</span> : String(v)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          </div>
        )}
      </Drawer>
    </div>
  );
}
