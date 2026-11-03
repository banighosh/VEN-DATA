import { ArrowDown, ArrowUp } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';
import { fmtValue } from '../../lib/format';
import type { ValueFormat } from '../../lib/types';
import { cx } from '../ui/primitives';

export interface Column<T> {
  key: string;
  label: string;
  format?: ValueFormat | 'text' | 'date' | 'signed';
  align?: 'left' | 'right';
  render?: (row: T) => ReactNode;
  sortValue?: (row: T) => number | string | null;
  width?: string;
}

function cell(v: unknown, format: Column<unknown>['format']): ReactNode {
  if (v === null || v === undefined || v === '') return <span className="text-ink-3">—</span>;
  if (format === 'text' || format === 'date' || typeof v !== 'number') return String(v);
  if (format === 'signed') return fmtValue(v, 'percent').replace(/^(?=\d)/, v > 0 ? '+' : '');
  return fmtValue(v, format ?? 'number', false);
}

export function DataTable<T extends Record<string, unknown>>({ rows, columns, maxHeight = 420, onRowClick, dense, initialSort, emptyText = 'No rows for the current filters.', rowKey, selectedKeys }: {
  rows: T[]; columns: Column<T>[]; maxHeight?: number; onRowClick?: (row: T) => void; dense?: boolean;
  initialSort?: { key: string; dir: 'asc' | 'desc' }; emptyText?: string; rowKey?: (row: T, i: number) => string; selectedKeys?: string[];
}) {
  const [sort, setSort] = useState(initialSort ?? null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    const get = (r: T) => (col?.sortValue ? col.sortValue(r) : (r[sort.key] as number | string | null));
    return [...rows].sort((a, b) => {
      const va = get(a), vb = get(b);
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      const c = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb));
      return sort.dir === 'asc' ? c : -c;
    });
  }, [rows, sort, columns]);

  if (!rows.length) return <p className="py-6 text-center text-sm text-ink-3">{emptyText}</p>;
  return (
    <div className="scroll-thin overflow-auto rounded-lg border border-line" style={{ maxHeight }}>
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-panel-2">
          <tr>
            {columns.map((c) => {
              const right = c.align === 'right' || (c.format && !['text', 'date'].includes(c.format));
              const active = sort?.key === c.key;
              return (
                <th key={c.key} scope="col" style={{ width: c.width }}
                  aria-sort={active ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                  className={cx('border-b border-line px-3 font-medium text-ink-2 whitespace-nowrap', dense ? 'py-1.5 text-xs' : 'py-2 text-xs', right ? 'text-right' : 'text-left')}>
                  <button className={cx('inline-flex items-center gap-1 hover:text-ink', right && 'flex-row-reverse')}
                    onClick={() => setSort((s) => (s?.key === c.key ? { key: c.key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key: c.key, dir: right ? 'desc' : 'asc' }))}>
                    {c.label}
                    {active ? (sort!.dir === 'asc' ? <ArrowUp size={12} /> : <ArrowDown size={12} />) : <span className="w-3" />}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="tnum">
          {sorted.map((r, i) => {
            const k = rowKey ? rowKey(r, i) : String(i);
            const selected = selectedKeys?.includes(k);
            return (
              <tr key={k} onClick={onRowClick ? () => onRowClick(r) : undefined}
                className={cx('border-b border-line last:border-0', onRowClick && 'cursor-pointer hover:bg-panel-2', selected && 'bg-accent-soft')}>
                {columns.map((c) => {
                  const right = c.align === 'right' || (c.format && !['text', 'date'].includes(c.format));
                  return (
                    <td key={c.key} className={cx('px-3 text-ink whitespace-nowrap', dense ? 'py-1.5' : 'py-2', right ? 'text-right' : 'text-left')}>
                      {c.render ? c.render(r) : cell(r[c.key], c.format)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
