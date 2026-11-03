import type { ValueFormat } from './types';

const currencyCode = () => {
  try { return localStorage.getItem('meridian.currency') || 'USD'; } catch { return 'USD'; }
};

export function fmtCurrency(v: number | null | undefined, compact = true): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: currencyCode(), notation: compact && Math.abs(v) >= 10_000 ? 'compact' : 'standard',
    maximumFractionDigits: compact && Math.abs(v) >= 10_000 ? 2 : Math.abs(v) < 100 && v !== 0 ? 2 : 0,
  }).format(v);
}

export function fmtNumber(v: number | null | undefined, compact = true, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return new Intl.NumberFormat('en-US', {
    notation: compact && Math.abs(v) >= 10_000 ? 'compact' : 'standard',
    maximumFractionDigits: compact && Math.abs(v) >= 10_000 ? (Math.abs(v) >= 1e6 ? 2 : 1) : digits,
  }).format(v);
}

export function fmtPercent(v: number | null | undefined, digits = 1, signed = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const s = `${(v * 100).toFixed(digits)}%`;
  return signed && v > 0 ? `+${s}` : s.replace('-', '−');
}

export function fmtPP(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const s = `${(v * 100).toFixed(digits)} pp`;
  return v > 0 ? `+${s}` : s.replace('-', '−');
}

export function fmtValue(v: number | null | undefined, format: ValueFormat | undefined, compact = true): string {
  switch (format) {
    case 'currency': return fmtCurrency(v, compact);
    case 'percent': return fmtPercent(v);
    case 'pp': return fmtPP(v);
    default: return fmtNumber(v, compact, v !== null && v !== undefined && Math.abs(v) < 10 && !Number.isInteger(v) ? 2 : 0);
  }
}

export function fmtChange(change: number | null | undefined, type: 'relative' | 'absolute' | undefined): string {
  if (change === null || change === undefined) return '—';
  return type === 'absolute' ? fmtPP(change) : fmtPercent(change, 1, true);
}

/** Axis ticks: whole numbers, compact once the axis reaches 10K. */
export function axisTick(format: ValueFormat | 'days' | undefined) {
  return (v: number) => {
    if (format === 'percent') return `${Math.round(v * 100)}%`;
    if (format === 'currency') {
      const abs = Math.abs(v);
      if (abs >= 1e9) return `$${(v / 1e9).toFixed(abs >= 1e10 ? 0 : 1)}B`;
      if (abs >= 1e6) return `$${(v / 1e6).toFixed(abs >= 1e7 ? 0 : 1)}M`;
      if (abs >= 1e4) return `$${Math.round(v / 1e3)}K`;
      return `$${Math.round(v).toLocaleString('en-US')}`;
    }
    const abs = Math.abs(v);
    if (abs >= 1e6) return `${(v / 1e6).toFixed(abs >= 1e7 ? 0 : 1)}M`;
    if (abs >= 1e4) return `${Math.round(v / 1e3)}K`;
    return Math.round(v).toLocaleString('en-US');
  };
}

export function fmtDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }): string {
  if (!iso) return '—';
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-GB', opts);
}

export function fmtBytes(n: number): string {
  if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${n} B`;
}

export const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
export const sentence = (s: string) => { const t = s.replace(/_/g, ' '); return t.charAt(0).toUpperCase() + t.slice(1); };
