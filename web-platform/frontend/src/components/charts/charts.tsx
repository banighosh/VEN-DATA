/* eslint-disable @typescript-eslint/no-explicit-any */
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Line, LineChart, Pie, PieChart,
  ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts';
import { useMemo, useState, type ReactNode } from 'react';
import { axisTick, fmtValue } from '../../lib/format';
import type { Pivot, ValueFormat } from '../../lib/types';
import { useApp } from '../../state/AppState';
import { cx } from '../ui/primitives';
import { useWidth } from './useWidth';

/* ------------------------------------------------------------------ shared pieces */
interface TipRow { name: string; value: number | null | undefined; color: string; format?: ValueFormat; dashed?: boolean; shape?: 'line' | 'block' }

export function TipBox({ title, rows, footer }: { title?: ReactNode; rows: TipRow[]; footer?: ReactNode }) {
  return (
    <div className="pointer-events-none min-w-[160px] rounded-lg border border-line bg-panel px-3 py-2 text-xs shadow-pop">
      {title && <p className="mb-1.5 font-semibold text-ink">{title}</p>}
      <div className="space-y-1">
        {rows.map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            {r.shape === 'block'
              ? <span className="h-2.5 w-2.5 shrink-0 rounded-[2px]" style={{ background: r.color }} />
              : <span className="h-0 w-3 shrink-0 border-t-2" style={{ borderColor: r.color, borderStyle: r.dashed ? 'dashed' : 'solid' }} />}
            <span className="tnum font-semibold text-ink">{fmtValue(r.value ?? null, r.format, false)}</span>
            <span className="truncate text-ink-2">{r.name}</span>
          </div>
        ))}
      </div>
      {footer && <p className="mt-1.5 border-t border-line pt-1.5 text-ink-3">{footer}</p>}
    </div>
  );
}

export function LegendRow({ items, className }: { items: { label: string; color: string; dashed?: boolean; shape?: 'line' | 'block' | 'dot' }[]; className?: string }) {
  return (
    <ul className={cx('flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2', className)} aria-label="Legend">
      {items.map((it) => (
        <li key={it.label} className="inline-flex items-center gap-1.5">
          {it.shape === 'block' ? <span className="h-2.5 w-2.5 rounded-[2px]" style={{ background: it.color }} />
            : it.shape === 'dot' ? <span className="h-2.5 w-2.5 rounded-full" style={{ background: it.color }} />
              : <span className="h-0 w-4 border-t-2" style={{ borderColor: it.color, borderStyle: it.dashed ? 'dashed' : 'solid' }} />}
          {it.label}
        </li>
      ))}
    </ul>
  );
}

function useAxis() {
  const { chart } = useApp();
  return {
    grid: <CartesianGrid stroke={chart.grid} vertical={false} />,
    tick: { fill: chart.tick, fontSize: 11 },
    axisLine: { stroke: chart.axis },
    chart,
  };
}

const labelWidth = (labels: string[]) => Math.min(170, Math.max(56, Math.max(0, ...labels.map((l) => l.length)) * 6.6 + 10));

/* ------------------------------------------------------------------ trend: current vs previous */
export function TrendChart({ data, format = 'currency', currentLabel, previousLabel, dataKeys = ['current', 'previous'], onSelect }: {
  data: Record<string, any>[]; format?: ValueFormat; currentLabel: string; previousLabel?: string;
  dataKeys?: [string, string]; onSelect?: (row: Record<string, any>) => void;
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  const hasPrev = !!previousLabel && data.some((d) => d[dataKeys[1]] !== null && d[dataKeys[1]] !== undefined);
  return (
    <div className="flex h-full flex-col">
      {hasPrev && <LegendRow className="mb-2" items={[{ label: currentLabel, color: chart.series[0] }, { label: previousLabel!, color: chart.previous, dashed: true }]} />}
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 22, left: 4, bottom: 0 }}
            onClick={(s: any) => { if (onSelect && s?.activePayload?.[0]) onSelect(s.activePayload[0].payload); }}>
            {grid}
            <XAxis dataKey="label" tick={tick} axisLine={axisLine} tickLine={false} minTickGap={18} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(format)} width={58} />
            <Tooltip cursor={{ stroke: chart.axis, strokeWidth: 1 }} content={({ active, payload, label }: any) => active && payload?.length ? (
              <TipBox title={label} rows={[
                { name: currentLabel, value: payload[0].payload[dataKeys[0]], color: chart.series[0], format },
                ...(hasPrev ? [{ name: payload[0].payload.previous_label ?? previousLabel!, value: payload[0].payload[dataKeys[1]], color: chart.previous, format, dashed: true }] : []),
              ]} />
            ) : null} />
            {hasPrev && <Line type="monotone" dataKey={dataKeys[1]} stroke={chart.previous} strokeWidth={2} strokeDasharray="5 4" dot={false} activeDot={false} isAnimationActive={false} connectNulls={false} />}
            <Line type="monotone" dataKey={dataKeys[0]} stroke={chart.series[0]} strokeWidth={2} dot={false}
              activeDot={{ r: 5, stroke: chart.surface, strokeWidth: 2, fill: chart.series[0] }} isAnimationActive={false} connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ horizontal ranked bars */
export function BarList({ rows, valueKey = 'revenue', format = 'currency', onSelect, selected = [], colorFor, secondary, height }: {
  rows: Record<string, any>[]; valueKey?: string; format?: ValueFormat; onSelect?: (key: string) => void; selected?: string[];
  colorFor?: (key: string) => string; secondary?: { key: string; label: string; format: ValueFormat }; height?: number;
}) {
  const { tick, chart } = useAxis();
  const w = labelWidth(rows.map((r) => String(r.key)));
  const h = height ?? Math.max(120, rows.length * 30 + 16);
  const hasSel = selected.length > 0;
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 64, left: 0, bottom: 0 }} barCategoryGap={6}
        onClick={(s: any) => { if (onSelect && s?.activeLabel) onSelect(String(s.activeLabel)); }}>
        <XAxis type="number" hide tickFormatter={axisTick(format)} domain={[0, 'auto']} />
        <YAxis type="category" dataKey="key" width={w} tick={{ ...tick, fill: chart.ink2 }} axisLine={false} tickLine={false} interval={0} />
        <Tooltip cursor={{ fill: chart.cursor }} content={({ active, payload }: any) => active && payload?.length ? (
          <TipBox title={payload[0].payload.key} rows={[
            { name: 'Value', value: payload[0].payload[valueKey], color: colorFor ? colorFor(payload[0].payload.key) : chart.series[0], format, shape: 'block' },
            ...(secondary ? [{ name: secondary.label, value: payload[0].payload[secondary.key], color: chart.previous, format: secondary.format, shape: 'block' as const }] : []),
          ]} footer={onSelect ? 'Click to filter' : undefined} />
        ) : null} />
        <Bar dataKey={valueKey} barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false} style={{ cursor: onSelect ? 'pointer' : 'default' }}>
          {rows.map((r) => (
            <Cell key={r.key} fill={colorFor ? colorFor(r.key) : chart.series[0]} fillOpacity={hasSel && !selected.includes(r.key) ? 0.35 : 1} />
          ))}
          <LabelList dataKey={valueKey} position="right" formatter={(v: any) => fmtValue(v, format)} style={{ fill: chart.ink2, fontSize: 11 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ vertical columns (supports signed values) */
export function ColumnChart({ data, dataKey, format = 'currency', labelKey = 'label', signed, onSelect, color, name = 'Value' }: {
  data: Record<string, any>[]; dataKey: string; format?: ValueFormat; labelKey?: string; signed?: boolean;
  onSelect?: (row: Record<string, any>) => void; color?: string; name?: string;
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  return (
    <ResponsiveContainer>
      <BarChart data={data} margin={{ top: 16, right: 8, left: 4, bottom: 0 }} barCategoryGap="22%"
        onClick={(s: any) => { if (onSelect && s?.activePayload?.[0]) onSelect(s.activePayload[0].payload); }}>
        {grid}
        <XAxis dataKey={labelKey} tick={tick} axisLine={axisLine} tickLine={false} minTickGap={8} />
        <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(format)} width={58} />
        {signed && <ReferenceLine y={0} stroke={chart.axis} />}
        <Tooltip cursor={{ fill: chart.cursor }} content={({ active, payload, label }: any) => active && payload?.length ? (
          <TipBox title={label} rows={[{ name, value: payload[0].value, color: signed ? (payload[0].value >= 0 ? chart.series[0] : chart.bad) : color ?? chart.series[0], format, shape: 'block' }]}
            footer={onSelect ? 'Click to drill in' : undefined} />
        ) : null} />
        <Bar dataKey={dataKey} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} style={{ cursor: onSelect ? 'pointer' : 'default' }}>
          {data.map((d, i) => <Cell key={i} fill={signed ? ((d[dataKey] ?? 0) >= 0 ? chart.series[0] : chart.bad) : color ?? chart.series[0]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ stacked columns (segment contribution) */
export function StackedColumns({ pivot, colorFor, format = 'currency', onSelectKey, percent }: {
  pivot: Pivot; colorFor: (key: string) => string; format?: ValueFormat; onSelectKey?: (key: string) => void; percent?: boolean;
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  const data = useMemo(() => {
    if (!percent) return pivot.rows;
    return pivot.rows.map((r) => {
      const total = pivot.keys.reduce((s, k) => s + ((r[k] as number) || 0), 0);
      const out: Record<string, any> = { ...r };
      pivot.keys.forEach((k) => { out[k] = total ? ((r[k] as number) || 0) / total : null; });
      return out;
    });
  }, [pivot, percent]);
  const fmt: ValueFormat = percent ? 'percent' : format;
  return (
    <div className="flex h-full flex-col">
      <LegendRow className="mb-2" items={pivot.keys.map((k) => ({ label: k, color: colorFor(k), shape: 'block' as const }))} />
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 4, right: 8, left: 4, bottom: 0 }} barCategoryGap="20%">
            {grid}
            <XAxis dataKey="label" tick={tick} axisLine={axisLine} tickLine={false} minTickGap={8} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(fmt)} width={58} domain={percent ? [0, 1] : [0, 'auto']} />
            <Tooltip cursor={{ fill: chart.cursor }} content={({ active, payload, label }: any) => active && payload?.length ? (
              <TipBox title={label} rows={[...payload].reverse().map((p: any) => ({ name: p.dataKey, value: p.value, color: colorFor(p.dataKey), format: fmt, shape: 'block' as const }))} />
            ) : null} />
            {pivot.keys.map((k, i) => (
              <Bar key={k} dataKey={k} stackId="s" fill={colorFor(k)} stroke={chart.surface} strokeWidth={1.5} maxBarSize={28}
                radius={i === pivot.keys.length - 1 ? [4, 4, 0, 0] : 0} isAnimationActive={false}
                onClick={onSelectKey ? () => onSelectKey(k) : undefined} style={{ cursor: onSelectKey ? 'pointer' : 'default' }} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ donut (composition) */
export function DonutChart({ rows, valueKey = 'revenue', format = 'currency', colorFor, onSelect, selected = [], centerLabel = 'Total' }: {
  rows: Record<string, any>[]; valueKey?: string; format?: ValueFormat; colorFor: (k: string) => string;
  onSelect?: (k: string) => void; selected?: string[]; centerLabel?: string;
}) {
  const { chart } = useApp();
  const [ref, width] = useWidth<HTMLDivElement>();
  const total = rows.reduce((s, r) => s + (r[valueKey] || 0), 0);
  const data = rows.filter((r) => (r[valueKey] || 0) > 0);
  const hasSel = selected.length > 0;
  const wide = width >= 460;
  const size = wide ? 190 : 170;
  return (
    <div ref={ref} className={cx('flex h-full gap-4', wide ? 'flex-row items-center' : 'flex-col items-stretch')}>
      <div className="relative mx-auto shrink-0" style={{ width: size, height: size }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie data={data} dataKey={valueKey} nameKey="key" innerRadius="64%" outerRadius="96%" startAngle={90} endAngle={-270}
              stroke={chart.surface} strokeWidth={2} isAnimationActive={false}
              onClick={(d: any) => onSelect?.(d.key ?? d.payload?.key)} style={{ cursor: onSelect ? 'pointer' : 'default' }}>
              {data.map((r) => <Cell key={r.key} fill={colorFor(r.key)} fillOpacity={hasSel && !selected.includes(r.key) ? 0.35 : 1} />)}
            </Pie>
            <Tooltip content={({ active, payload }: any) => active && payload?.length ? (
              <TipBox title={payload[0].payload.key} rows={[
                { name: 'Value', value: payload[0].value, color: colorFor(payload[0].payload.key), format, shape: 'block' },
                { name: 'Share', value: total ? payload[0].value / total : null, color: 'transparent', format: 'percent', shape: 'block' },
              ]} />
            ) : null} />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xs text-ink-3">{centerLabel}</span>
          <span className="text-md font-semibold">{fmtValue(total, format)}</span>
        </div>
      </div>
      <ul className="min-w-0 flex-1 space-y-1.5 text-sm">
        {rows.map((r) => (
          <li key={r.key}>
            <button onClick={() => onSelect?.(r.key)} disabled={!onSelect}
              className={cx('flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left', onSelect && 'hover:bg-panel-2',
                hasSel && !selected.includes(r.key) && 'opacity-50')}>
              <span className="h-2.5 w-2.5 shrink-0 rounded-[2px]" style={{ background: colorFor(r.key) }} />
              <span className="min-w-0 flex-1 truncate text-ink">{r.key}</span>
              <span className="tnum text-ink-2">{fmtValue(total ? (r[valueKey] || 0) / total : null, 'percent')}</span>
              <span className="tnum w-20 text-right font-medium">{fmtValue(r[valueKey], format)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ cumulative area */
export function CumulativeArea({ data, currentLabel, previousLabel, format = 'currency' }: {
  data: Record<string, any>[]; currentLabel: string; previousLabel?: string; format?: ValueFormat;
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  const hasPrev = !!previousLabel && data.some((d) => d.previous);
  return (
    <div className="flex h-full flex-col">
      <LegendRow className="mb-2" items={[{ label: `${currentLabel} cumulative`, color: chart.series[0] },
        ...(hasPrev ? [{ label: `${previousLabel} cumulative`, color: chart.previous, dashed: true }] : [])]} />
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 8, right: 22, left: 4, bottom: 0 }}>
            {grid}
            <XAxis dataKey="label" tick={tick} axisLine={axisLine} tickLine={false} minTickGap={18} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(format)} width={58} />
            <Tooltip cursor={{ stroke: chart.axis }} content={({ active, payload, label }: any) => active && payload?.length ? (
              <TipBox title={label} rows={[{ name: currentLabel, value: payload[0].payload.current, color: chart.series[0], format },
                ...(hasPrev ? [{ name: previousLabel!, value: payload[0].payload.previous, color: chart.previous, format, dashed: true }] : [])]} />
            ) : null} />
            {hasPrev && <Area type="monotone" dataKey="previous" stroke={chart.previous} strokeDasharray="5 4" strokeWidth={2} fill="transparent" isAnimationActive={false} />}
            <Area type="monotone" dataKey="current" stroke={chart.series[0]} strokeWidth={2} fill={chart.series[0]} fillOpacity={0.1} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ scatter (relationships) */
export function ScatterPlot({ points, xLabel, yLabel, xFormat = 'currency', yFormat = 'percent', zLabel, zFormat = 'number', colorFor, onSelect, labelTop = 3 }: {
  points: { key: string; x: number; y: number; z?: number; group?: string }[]; xLabel: string; yLabel: string;
  xFormat?: ValueFormat; yFormat?: ValueFormat; zLabel?: string; zFormat?: ValueFormat; colorFor: (g: string) => string;
  onSelect?: (key: string) => void; labelTop?: number;
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  const groups = [...new Set(points.map((p) => p.group ?? 'All'))];
  const byX = [...points].sort((a, b) => b.x - a.x);
  const labelled = new Set(byX.slice(0, labelTop).map((p) => p.key));
  const rightmost = byX[0]?.key; // label the right-most point on its left so it never clips
  return (
    <div className="flex h-full flex-col">
      {groups.length > 1 && <LegendRow className="mb-2" items={groups.map((g) => ({ label: g, color: colorFor(g), shape: 'dot' as const }))} />}
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 12, right: 24, left: 4, bottom: 18 }}>
            {grid}
            <XAxis type="number" dataKey="x" name={xLabel} tick={tick} axisLine={axisLine} tickLine={false} tickFormatter={axisTick(xFormat)}
              label={{ value: xLabel, position: 'insideBottom', offset: -10, fill: chart.tick, fontSize: 11 }} domain={['auto', 'auto']} />
            <YAxis type="number" dataKey="y" name={yLabel} tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(yFormat)} width={58}
              label={{ value: yLabel, angle: -90, position: 'insideLeft', offset: 12, fill: chart.tick, fontSize: 11 }} domain={['auto', 'auto']} />
            <ZAxis type="number" dataKey="z" range={[70, 420]} />
            <Tooltip cursor={{ stroke: chart.axis, strokeDasharray: '3 3' }} content={({ active, payload }: any) => active && payload?.length ? (
              <TipBox title={payload[0].payload.key} rows={[
                { name: xLabel, value: payload[0].payload.x, color: colorFor(payload[0].payload.group ?? 'All'), format: xFormat, shape: 'block' },
                { name: yLabel, value: payload[0].payload.y, color: 'transparent', format: yFormat, shape: 'block' },
                ...(zLabel ? [{ name: zLabel, value: payload[0].payload.z, color: 'transparent', format: zFormat, shape: 'block' as const }] : []),
              ]} footer={onSelect ? 'Click to filter' : undefined} />
            ) : null} />
            {groups.map((g) => (
              <Scatter key={g} name={g} data={points.filter((p) => (p.group ?? 'All') === g)} fill={colorFor(g)} isAnimationActive={false}
                stroke={chart.surface} strokeWidth={2} onClick={(d: any) => onSelect?.(d.key ?? d.payload?.key)} style={{ cursor: onSelect ? 'pointer' : 'default' }}>
                <LabelList dataKey="key" content={(p: any) => labelled.has(p.value) ? (
                  p.value === rightmost
                    ? <text x={p.x + p.width / 2 - 10} y={p.y + p.height / 2 + 4} textAnchor="end" fill={chart.ink2} fontSize={11}>{p.value}</text>
                    : <text x={p.x + p.width / 2 + 9} y={p.y + p.height / 2 + 4} fill={chart.ink2} fontSize={11}>{p.value}</text>
                ) : null} />
              </Scatter>
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ waterfall (financial movements) */
export function Waterfall({ steps, format = 'currency', mode = 'signed' }: {
  steps: { name: string; value: number; kind: 'total' | 'delta' }[]; format?: ValueFormat; mode?: 'signed' | 'cost';
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  const data = useMemo(() => {
    let running = 0;
    return steps.map((s) => {
      if (s.kind === 'total') { running = s.value; return { ...s, base: Math.min(0, s.value), bar: Math.abs(s.value), end: s.value }; }
      const start = running;
      running += s.value;
      return { ...s, base: Math.min(start, running), bar: Math.abs(s.value), end: running };
    });
  }, [steps]);
  const colorOf = (d: { kind: string; value: number }) =>
    d.kind === 'total' ? chart.total : mode === 'cost' ? chart.deduct : d.value >= 0 ? chart.good : chart.bad;
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div className="flex h-full flex-col">
      <LegendRow className="mb-2" items={mode === 'cost'
        ? [{ label: 'Total', color: chart.total, shape: 'block' }, { label: 'Deduction', color: chart.deduct, shape: 'block' }]
        : [{ label: 'Total', color: chart.total, shape: 'block' }, { label: 'Increase', color: chart.good, shape: 'block' }, { label: 'Decrease', color: chart.bad, shape: 'block' }]} />
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 18, right: 8, left: 4, bottom: 0 }} barCategoryGap="18%"
            onMouseMove={(s: any) => setHover(s?.activeTooltipIndex ?? null)} onMouseLeave={() => setHover(null)}>
            {grid}
            <XAxis dataKey="name" tick={(p: any) => <WrapTick {...p} fill={chart.tick} />} axisLine={axisLine} tickLine={false} interval={0} height={40} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(format)} width={58} />
            <Tooltip cursor={{ fill: chart.cursor }} content={({ active, payload }: any) => active && payload?.length ? (
              <TipBox title={payload[0].payload.name} rows={[
                { name: payload[0].payload.kind === 'total' ? 'Total' : 'Change', value: payload[0].payload.value, color: colorOf(payload[0].payload), format, shape: 'block' },
                ...(payload[0].payload.kind === 'delta' ? [{ name: 'Running total', value: payload[0].payload.end, color: 'transparent', format, shape: 'block' as const }] : []),
              ]} />
            ) : null} />
            <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
            <Bar dataKey="bar" stackId="w" maxBarSize={36} radius={[3, 3, 3, 3]} isAnimationActive={false}>
              {data.map((d, i) => <Cell key={i} fill={colorOf(d)} fillOpacity={hover === null || hover === i ? 1 : 0.75} />)}
              <LabelList dataKey="value" position="top" formatter={(v: any) => fmtValue(v, format)} style={{ fill: chart.ink2, fontSize: 10.5 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function WrapTick({ x, y, payload, fill }: any) {
  const words = String(payload.value).replace(' · ', ' ').split(' ');
  const lines: string[] = [];
  let cur = '';
  for (const w of words) { if ((cur + ' ' + w).trim().length > 13 && cur) { lines.push(cur); cur = w; } else cur = (cur + ' ' + w).trim(); }
  if (cur) lines.push(cur);
  return (
    <text x={x} y={y + 10} textAnchor="middle" fill={fill} fontSize={10.5}>
      {lines.slice(0, 2).map((l, i) => <tspan key={i} x={x} dy={i ? 12 : 0}>{l}</tspan>)}
    </text>
  );
}

/* ------------------------------------------------------------------ forecast */
export function ForecastChart({ history, forecast, format = 'currency' }: {
  history: { label: string; actual: number }[]; forecast: { label: string; forecast: number; lower: number; upper: number }[]; format?: ValueFormat;
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  const data = useMemo(() => {
    const h = history.map((p) => ({ label: p.label, actual: p.actual } as Record<string, any>));
    if (h.length) h[h.length - 1].forecast = h[h.length - 1].actual;
    return [...h, ...forecast.map((f) => ({ label: f.label, forecast: f.forecast, band: [f.lower, f.upper], lower: f.lower, upper: f.upper }))];
  }, [history, forecast]);
  return (
    <div className="flex h-full flex-col">
      <LegendRow className="mb-2" items={[{ label: 'Actual', color: chart.series[0] }, { label: 'Forecast', color: chart.series[0], dashed: true },
        { label: '80% interval', color: chart.series[0] + '33', shape: 'block' }]} />
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 22, left: 4, bottom: 0 }}>
            {grid}
            <XAxis dataKey="label" tick={tick} axisLine={axisLine} tickLine={false} minTickGap={18} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(format)} width={58} />
            <Tooltip cursor={{ stroke: chart.axis }} content={({ active, payload, label }: any) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload;
              return <TipBox title={label} rows={p.actual !== undefined
                ? [{ name: 'Actual', value: p.actual, color: chart.series[0], format }]
                : [{ name: 'Forecast', value: p.forecast, color: chart.series[0], format, dashed: true },
                  { name: 'Low (80%)', value: p.lower, color: 'transparent', format }, { name: 'High (80%)', value: p.upper, color: 'transparent', format }]} />;
            }} />
            <Area dataKey="band" stroke="none" fill={chart.series[0]} fillOpacity={0.14} isAnimationActive={false} />
            <Line dataKey="actual" stroke={chart.series[0]} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="forecast" stroke={chart.series[0]} strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ pareto (share + cumulative share, one % axis) */
export function ParetoChart({ rows, onSelect }: { rows: { key: string; share: number | null; cumulative_share: number }[]; onSelect?: (k: string) => void }) {
  const { grid, tick, axisLine, chart } = useAxis();
  return (
    <div className="flex h-full flex-col">
      <LegendRow className="mb-2" items={[{ label: 'Share of revenue', color: chart.series[0], shape: 'block' }, { label: 'Cumulative share', color: chart.ink2 }]} />
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 8, right: 34, left: 4, bottom: 0 }}
            onClick={(s: any) => { if (onSelect && s?.activeLabel) onSelect(String(s.activeLabel)); }}>
            {grid}
            <XAxis dataKey="key" tick={tick} axisLine={axisLine} tickLine={false} interval={0} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick('percent')} domain={[0, 1]} width={44} />
            <ReferenceLine y={0.8} stroke={chart.axis} strokeDasharray="4 4" label={{ value: '80%', position: 'right', fill: chart.tick, fontSize: 10 }} />
            <Tooltip cursor={{ fill: chart.cursor }} content={({ active, payload, label }: any) => active && payload?.length ? (
              <TipBox title={label} rows={[{ name: 'Share', value: payload[0].payload.share, color: chart.series[0], format: 'percent', shape: 'block' },
                { name: 'Cumulative', value: payload[0].payload.cumulative_share, color: chart.ink2, format: 'percent' }]} />
            ) : null} />
            <Bar dataKey="share" fill={chart.series[0]} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} style={{ cursor: onSelect ? 'pointer' : 'default' }} />
            <Line dataKey="cumulative_share" stroke={chart.ink2} strokeWidth={2} dot={{ r: 3.5, fill: chart.ink2, stroke: chart.surface, strokeWidth: 2 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ grouped columns: current vs previous */
export function GroupedColumns({ rows, currentLabel, previousLabel, format = 'currency', onSelect, selected = [] }: {
  rows: { key: string; current: number | null; previous: number | null }[]; currentLabel: string; previousLabel?: string;
  format?: ValueFormat; onSelect?: (k: string) => void; selected?: string[];
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  const hasPrev = !!previousLabel;
  return (
    <div className="flex h-full flex-col">
      <LegendRow className="mb-2" items={[{ label: currentLabel, color: chart.series[0], shape: 'block' },
        ...(hasPrev ? [{ label: previousLabel!, color: chart.previous, shape: 'block' as const }] : [])]} />
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 4, bottom: 0 }} barGap={2} barCategoryGap="24%"
            onClick={(s: any) => { if (onSelect && s?.activeLabel) onSelect(String(s.activeLabel)); }}>
            {grid}
            <XAxis dataKey="key" tick={tick} axisLine={axisLine} tickLine={false} interval={0} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(format)} width={58} />
            <Tooltip cursor={{ fill: chart.cursor }} content={({ active, payload, label }: any) => active && payload?.length ? (
              <TipBox title={label} rows={[{ name: currentLabel, value: payload[0].payload.current, color: chart.series[0], format, shape: 'block' },
                ...(hasPrev ? [{ name: previousLabel!, value: payload[0].payload.previous, color: chart.previous, format, shape: 'block' as const }] : [])]}
                footer={onSelect ? 'Click to drill in' : undefined} />
            ) : null} />
            {hasPrev && <Bar dataKey="previous" fill={chart.previous} maxBarSize={22} radius={[4, 4, 0, 0]} isAnimationActive={false} />}
            <Bar dataKey="current" fill={chart.series[0]} maxBarSize={22} radius={[4, 4, 0, 0]} isAnimationActive={false} style={{ cursor: onSelect ? 'pointer' : 'default' }}>
              {rows.map((r) => <Cell key={r.key} fillOpacity={selected.length && !selected.includes(r.key) ? 0.4 : 1} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ multi-line (per-entity trends) */
export function MultiLine({ pivot, colorFor, format = 'currency', onSelectKey, emphasis }: {
  pivot: Pivot; colorFor: (k: string) => string; format?: ValueFormat; onSelectKey?: (k: string) => void; emphasis?: string[];
}) {
  const { grid, tick, axisLine, chart } = useAxis();
  const [focus, setFocus] = useState<string | null>(null);
  const emph = focus ? [focus] : emphasis ?? [];
  return (
    <div className="flex h-full flex-col">
      <ul className="mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-2" aria-label="Legend">
        {pivot.keys.map((k) => (
          <li key={k}>
            <button onMouseEnter={() => setFocus(k)} onMouseLeave={() => setFocus(null)} onFocus={() => setFocus(k)} onBlur={() => setFocus(null)}
              onClick={() => onSelectKey?.(k)} className="inline-flex items-center gap-1.5 rounded px-1 hover:text-ink">
              <span className="h-0 w-4 border-t-2" style={{ borderColor: colorFor(k) }} />{k}
            </button>
          </li>
        ))}
      </ul>
      <div className="min-h-0 flex-1">
        <ResponsiveContainer>
          <LineChart data={pivot.rows} margin={{ top: 8, right: 22, left: 4, bottom: 0 }}>
            {grid}
            <XAxis dataKey="label" tick={tick} axisLine={axisLine} tickLine={false} minTickGap={18} />
            <YAxis tick={tick} axisLine={false} tickLine={false} tickFormatter={axisTick(format)} width={58} />
            <Tooltip cursor={{ stroke: chart.axis }} content={({ active, payload, label }: any) => active && payload?.length ? (
              <TipBox title={label} rows={[...payload].sort((a: any, b: any) => (b.value ?? 0) - (a.value ?? 0)).map((p: any) => ({ name: p.dataKey, value: p.value, color: colorFor(p.dataKey), format }))} />
            ) : null} />
            {pivot.keys.map((k) => (
              <Line key={k} dataKey={k} stroke={colorFor(k)} strokeWidth={2} dot={false} isAnimationActive={false}
                strokeOpacity={emph.length && !emph.includes(k) ? 0.25 : 1} activeDot={{ r: 4, stroke: chart.surface, strokeWidth: 2 }} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ sparkline */
export function Sparkline({ data, color, height = 34 }: { data: { label: string; value: number | null }[]; color: string; height?: number }) {
  const pts = data.filter((d) => d.value !== null);
  if (pts.length < 2) return <div style={{ height }} />;
  return (
    <div style={{ height }} aria-hidden="true">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <YAxis hide domain={['dataMin', 'dataMax']} />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} fill={color} fillOpacity={0.08} dot={false} isAnimationActive={false} connectNulls={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
