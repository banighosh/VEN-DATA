/**
 * Chart palette. Categorical order is fixed (validated for CVD separation on the
 * app's own light #ffffff and dark #111a2e surfaces). Colors follow the entity,
 * never its rank in the current filter, so a filter never repaints survivors.
 */
export const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
};

// Sequential blue ramp (magnitude): light → dark.
export const SEQ_BLUE = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6',
  '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b'];
// Diverging arms (polarity): red ← gray → blue.
const RED_ARM = ['#fbe0de', '#f6b9b5', '#ee8c86', '#e45f59', '#c9403b', '#a32c28'];
const BLUE_ARM = ['#d8e7fa', '#a9cbf3', '#74a9ea', '#3f86df', '#2468bd', '#164f95'];

export const STATUS = { good: '#0ca30c', warning: '#fab219', serious: '#ec835a', critical: '#d03b3b' };

export type ThemeName = 'light' | 'dark';

export function chartTheme(t: ThemeName) {
  const dark = t === 'dark';
  return {
    name: t,
    series: SERIES[t],
    surface: dark ? '#111a2e' : '#ffffff',
    grid: dark ? '#1f2b42' : '#e9edf2',
    axis: dark ? '#2f405f' : '#cbd3de',
    tick: dark ? '#8090aa' : '#6f7c92',
    ink: dark ? '#e6ebf2' : '#1e2532',
    ink2: dark ? '#aab7cb' : '#4e5b70',
    muted: dark ? '#4d5d7a' : '#b4bfcf',
    previous: dark ? '#6c7e9b' : '#9aa7bb',
    neutralMid: dark ? '#26324a' : '#eef0f3',
    cursor: dark ? 'rgba(255,255,255,0.06)' : 'rgba(11,31,58,0.05)',
    good: dark ? '#3cc27a' : '#0f8a43',
    bad: dark ? '#f07a70' : '#d03b3b',
    total: dark ? '#3987e5' : '#2a78d6',
    deduct: dark ? '#56698a' : '#9aa7bb',
  };
}
export type ChartTheme = ReturnType<typeof chartTheme>;

/** Sequential color for a value in [min, max]. */
export function seqColor(v: number | null | undefined, min: number, max: number, dark: boolean): string {
  if (v === null || v === undefined || Number.isNaN(v)) return dark ? '#1a2540' : '#f1f3f6';
  const t = max > min ? (v - min) / (max - min) : 0.5;
  if (dark) return darkSeq(t);
  const ramp = SEQ_BLUE.slice(0, 11);
  return ramp[Math.min(ramp.length - 1, Math.max(0, Math.round(t * (ramp.length - 1))))];
}

function darkSeq(t: number): string {
  // On the dark surface magnitude reads as light-on-dark: near-zero recedes toward the surface.
  const ramp = ['#16284a', '#1a3460', '#1c4278', '#1f5194', '#2763b0', '#3577cc', '#4a8ce0', '#6aa3ea', '#8fbbf1', '#b5d3f7'];
  return ramp[Math.min(ramp.length - 1, Math.max(0, Math.round(t * (ramp.length - 1))))];
}

/** Diverging color: negative → red arm, ~0 → neutral gray, positive → blue arm. */
export function divColor(v: number | null | undefined, maxAbs: number, dark: boolean): string {
  if (v === null || v === undefined || Number.isNaN(v)) return dark ? '#1a2540' : '#f1f3f6';
  const mid = dark ? '#26324a' : '#eef0f3';
  if (maxAbs <= 0 || Math.abs(v) < maxAbs * 0.04) return mid;
  const t = Math.min(1, Math.abs(v) / maxAbs);
  const arm = v < 0 ? RED_ARM : BLUE_ARM;
  return arm[Math.min(arm.length - 1, Math.floor(t * arm.length))];
}

/** Text color to sit inside a filled cell. */
export function inkOn(hex: string): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16) / 255, g = parseInt(h.slice(2, 4), 16) / 255, b = parseInt(h.slice(4, 6), 16) / 255;
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const L = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  return L > 0.42 ? '#0b1220' : '#ffffff';
}
