import { useMemo, useState } from 'react';
import { divColor, inkOn, seqColor } from '../../lib/chartTheme';
import { fmtValue } from '../../lib/format';
import type { BreakdownRow, ValueFormat } from '../../lib/types';
import { useApp } from '../../state/AppState';
import { TipBox } from './charts';
import { useWidth } from './useWidth';

// Equal-area tile grid of US states (col, row). Every state gets the same visual weight,
// so small high-revenue states (e.g. RI, DE) are as readable as large ones.
const GRID: Record<string, [number, number]> = {
  AK: [0, 0], ME: [11, 0], VT: [10, 1], NH: [11, 1],
  WA: [1, 2], ID: [2, 2], MT: [3, 2], ND: [4, 2], MN: [5, 2], IL: [6, 2], WI: [7, 2], MI: [8, 2], NY: [9, 2], RI: [10, 2], MA: [11, 2],
  OR: [1, 3], NV: [2, 3], WY: [3, 3], SD: [4, 3], IA: [5, 3], IN: [6, 3], OH: [7, 3], PA: [8, 3], NJ: [9, 3], CT: [10, 3],
  CA: [1, 4], UT: [2, 4], CO: [3, 4], NE: [4, 4], MO: [5, 4], KY: [6, 4], WV: [7, 4], VA: [8, 4], MD: [9, 4], DE: [10, 4],
  AZ: [2, 5], NM: [3, 5], KS: [4, 5], AR: [5, 5], TN: [6, 5], NC: [7, 5], SC: [8, 5], DC: [9, 5],
  OK: [4, 6], LA: [5, 6], MS: [6, 6], AL: [7, 6], GA: [8, 6],
  HI: [0, 7], TX: [4, 7], FL: [9, 7],
};

export const STATE_ABBR: Record<string, string> = {
  Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA', Colorado: 'CO', Connecticut: 'CT', Delaware: 'DE',
  'District of Columbia': 'DC', Florida: 'FL', Georgia: 'GA', Hawaii: 'HI', Idaho: 'ID', Illinois: 'IL', Indiana: 'IN', Iowa: 'IA',
  Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA', Maine: 'ME', Maryland: 'MD', Massachusetts: 'MA', Michigan: 'MI', Minnesota: 'MN',
  Mississippi: 'MS', Missouri: 'MO', Montana: 'MT', Nebraska: 'NE', Nevada: 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ',
  'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', Ohio: 'OH', Oklahoma: 'OK', Oregon: 'OR',
  Pennsylvania: 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD', Tennessee: 'TN', Texas: 'TX', Utah: 'UT',
  Vermont: 'VT', Virginia: 'VA', Washington: 'WA', 'West Virginia': 'WV', Wisconsin: 'WI', Wyoming: 'WY',
};

/** True when most state names are recognisable US states (otherwise the caller shows a ranked list). */
export function isUsStates(names: string[]): boolean {
  if (!names.length) return false;
  const hits = names.filter((n) => STATE_ABBR[n] || GRID[n.toUpperCase()]).length;
  return hits / names.length >= 0.8;
}

export type MapMetric = 'revenue' | 'growth' | 'margin';

export function TileMap({ rows, metric, onSelect, selected = [] }: {
  rows: BreakdownRow[]; metric: MapMetric; onSelect?: (state: string) => void; selected?: string[];
}) {
  const { chart, theme } = useApp();
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<{ x: number; y: number; row: BreakdownRow | null; name: string } | null>(null);
  const byAbbr = useMemo(() => {
    const m = new Map<string, BreakdownRow>();
    rows.forEach((r) => { const a = STATE_ABBR[r.key] ?? r.key.toUpperCase(); m.set(a, r); });
    return m;
  }, [rows]);
  const nameOf = useMemo(() => Object.fromEntries(Object.entries(STATE_ABBR).map(([n, a]) => [a, n])), []);
  const val = (r: BreakdownRow | undefined) => (r ? (metric === 'revenue' ? r.revenue : metric === 'growth' ? r.growth ?? null : r.margin) : null);
  const values = rows.map((r) => val(r)).filter((v): v is number => v !== null && v !== undefined);
  const min = Math.min(...values), max = Math.max(...values), maxAbs = Math.max(...values.map(Math.abs), 0.0001);
  const fmt: ValueFormat = metric === 'revenue' ? 'currency' : 'percent';
  const color = (v: number | null) => (metric === 'growth' ? divColor(v, maxAbs, theme === 'dark') : seqColor(v, min, max, theme === 'dark'));
  const size = Math.min(56, Math.floor(width / 12.3));
  const gap = 3;
  const svgW = 12 * (size + gap), svgH = 8 * (size + gap);
  const hasSel = selected.length > 0;

  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)}>
      <svg data-chart-root width={svgW} height={svgH} role="img" aria-label={`US map of ${metric} by state`} className="mx-auto block">
        {Object.entries(GRID).map(([abbr, [c, r]]) => {
          const row = byAbbr.get(abbr);
          const v = val(row);
          const fill = row ? color(v) : (theme === 'dark' ? '#152038' : '#f1f3f6');
          const name = row?.key ?? nameOf[abbr] ?? abbr;
          const dim = hasSel && !selected.includes(name);
          return (
            <g key={abbr} transform={`translate(${c * (size + gap)}, ${r * (size + gap)})`}
              onMouseMove={(e) => { const b = ref.current!.getBoundingClientRect(); setTip({ x: e.clientX - b.left, y: e.clientY - b.top, row: row ?? null, name }); }}
              onClick={() => row && onSelect?.(row.key)} style={{ cursor: row && onSelect ? 'pointer' : 'default' }} opacity={dim ? 0.35 : 1}>
              <rect width={size} height={size} rx={5} fill={fill} stroke={selected.includes(name) ? chart.ink : 'none'} strokeWidth={2} />
              <text x={size / 2} y={size / 2 - (size > 40 ? 2 : -4)} textAnchor="middle" fontSize={size > 40 ? 11 : 9.5} fontWeight={600} fill={row ? inkOn(fill) : chart.tick}>{abbr}</text>
              {size > 40 && row && (
                <text x={size / 2} y={size / 2 + 12} textAnchor="middle" fontSize={9} fill={inkOn(fill)} className="tnum">{fmtValue(v, fmt)}</text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="mt-2 flex items-center justify-center gap-2 text-2xs text-ink-3">
        <span>{fmtValue(metric === 'growth' ? -maxAbs : min, fmt)}</span>
        <span className="h-2 w-32 rounded-full" style={{ background: `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1].map((t) => color(metric === 'growth' ? -maxAbs + t * 2 * maxAbs : min + t * (max - min))).join(',')})` }} />
        <span>{fmtValue(metric === 'growth' ? maxAbs : max, fmt)}</span>
        <span className="ml-3 inline-flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-[2px] border border-line" style={{ background: theme === 'dark' ? '#152038' : '#f1f3f6' }} />No sales</span>
      </div>
      {tip && (
        <div className="absolute z-20" style={{ left: Math.min(tip.x + 12, width - 200), top: tip.y + 12 }}>
          {tip.row ? (
            <TipBox title={tip.name} rows={[
              { name: 'Revenue', value: tip.row.revenue, color: color(val(tip.row)), format: 'currency', shape: 'block' },
              { name: 'Share', value: tip.row.share, color: 'transparent', format: 'percent', shape: 'block' },
              { name: 'Margin', value: tip.row.margin, color: 'transparent', format: 'percent', shape: 'block' },
              { name: 'Growth', value: tip.row.growth ?? null, color: 'transparent', format: 'percent', shape: 'block' },
            ]} footer={onSelect ? 'Click to filter' : undefined} />
          ) : <TipBox title={tip.name} rows={[]} footer="No sales in this period" />}
        </div>
      )}
    </div>
  );
}
