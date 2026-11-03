import { useMemo, useState } from 'react';
import { useWidth } from './useWidth';
import { divColor, inkOn, seqColor } from '../../lib/chartTheme';
import { fmtValue } from '../../lib/format';
import type { Matrix, ValueFormat } from '../../lib/types';
import { useApp } from '../../state/AppState';
import { TipBox } from './charts';

export { useWidth } from './useWidth';

/** Row × column heat map drawn as SVG (so it exports like every other chart). */
export function Heatmap({ matrix, format = 'currency', onSelectRow, diverging, rowLabelWidth }: {
  matrix: Matrix; format?: ValueFormat; onSelectRow?: (row: string) => void; diverging?: boolean; rowLabelWidth?: number;
}) {
  const { chart, theme } = useApp();
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<{ x: number; y: number; row: string; col: string; value: number | null } | null>(null);
  const lookup = useMemo(() => new Map(matrix.cells.map((c) => [`${c.row}|${c.col}`, c.value])), [matrix]);
  const values = matrix.cells.map((c) => c.value).filter((v): v is number => v !== null);
  const min = Math.min(...values), max = Math.max(...values);
  const maxAbs = Math.max(...values.map(Math.abs));
  const labelW = rowLabelWidth ?? Math.min(170, Math.max(48, ...matrix.rows.map((r) => r.length * 6.6 + 12)));
  const headH = 22;
  const cellW = Math.max(18, (width - labelW) / Math.max(1, matrix.cols.length));
  const cellH = Math.min(34, Math.max(22, 260 / Math.max(1, matrix.rows.length)));
  const height = headH + cellH * matrix.rows.length + 2;
  const showText = cellW >= 46;
  const every = Math.ceil(42 / cellW);
  const color = (v: number | null) => (diverging ? divColor(v, maxAbs, theme === 'dark') : seqColor(v, min, max, theme === 'dark'));

  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)}>
      <svg data-chart-root width={width} height={height} role="img" aria-label="Heat map">
        {matrix.cols.map((c, j) => (j % every === 0 ? (
          <text key={c} x={labelW + j * cellW + cellW / 2} y={14} textAnchor="middle" fontSize={10.5} fill={chart.tick}>{c}</text>
        ) : null))}
        {matrix.rows.map((r, i) => (
          <g key={r} transform={`translate(0, ${headH + i * cellH})`}>
            <text x={labelW - 8} y={cellH / 2 + 4} textAnchor="end" fontSize={11} fill={chart.ink2}
              style={{ cursor: onSelectRow ? 'pointer' : 'default' }} onClick={() => onSelectRow?.(r)}>{r}</text>
            {matrix.cols.map((c, j) => {
              const v = lookup.get(`${r}|${c}`) ?? null;
              const fill = color(v);
              return (
                <g key={c} onMouseMove={(e) => {
                  const box = ref.current!.getBoundingClientRect();
                  setTip({ x: e.clientX - box.left, y: e.clientY - box.top, row: r, col: c, value: v });
                }} onClick={() => onSelectRow?.(r)} style={{ cursor: onSelectRow ? 'pointer' : 'default' }}>
                  <rect x={labelW + j * cellW + 1} y={1} width={cellW - 2} height={cellH - 2} rx={3} fill={fill} />
                  {showText && v !== null && (
                    <text x={labelW + j * cellW + cellW / 2} y={cellH / 2 + 4} textAnchor="middle" fontSize={10} fill={inkOn(fill)} className="tnum">
                      {fmtValue(v, format)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <div className="mt-2 flex items-center gap-2 text-2xs text-ink-3">
        <span>{diverging ? fmtValue(-maxAbs, format) : fmtValue(min, format)}</span>
        <span className="h-2 w-28 rounded-full" style={{ background: `linear-gradient(90deg, ${[0, 0.25, 0.5, 0.75, 1].map((t) => color(diverging ? -maxAbs + t * 2 * maxAbs : min + t * (max - min))).join(',')})` }} />
        <span>{diverging ? fmtValue(maxAbs, format) : fmtValue(max, format)}</span>
      </div>
      {tip && (
        <div className="absolute z-20" style={{ left: Math.min(tip.x + 12, width - 190), top: tip.y + 12 }}>
          <TipBox title={`${tip.row}, ${tip.col}`} rows={[{ name: matrix.measure ?? 'Value', value: tip.value, color: color(tip.value), format, shape: 'block' }]} />
        </div>
      )}
    </div>
  );
}
