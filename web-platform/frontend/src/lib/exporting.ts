import { saveBlob } from './api';

/** Export the first chart SVG inside `container` as a 2× PNG on the chart surface color. */
export async function exportChartPng(container: HTMLElement, name: string, background: string, subtitle = '', ink = '#1e2532', muted = '#6f7c92'): Promise<void> {
  const svg = container.querySelector('svg[data-chart-root], svg.recharts-surface, svg') as SVGSVGElement | null;
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', String(rect.width));
  clone.setAttribute('height', String(rect.height));
  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
  style.textContent = `text{font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:12px}`;
  clone.insertBefore(style, clone.firstChild);
  const xml = new XMLSerializer().serializeToString(clone);
  const img = new Image();
  const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }));
  await new Promise<void>((resolve, reject) => { img.onload = () => resolve(); img.onerror = () => reject(new Error('render failed')); img.src = url; });
  const scale = 2, pad = 20, head = subtitle ? 52 : 36;
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil((rect.width + pad * 2) * scale);
  canvas.height = Math.ceil((rect.height + head + pad * 2) * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.scale(scale, scale);
  // Title and period travel with the image so it stands on its own in a deck or email.
  ctx.fillStyle = ink;
  ctx.font = '600 15px "IBM Plex Sans", system-ui, sans-serif';
  ctx.fillText(name, pad, pad + 14);
  if (subtitle) { ctx.fillStyle = muted; ctx.font = '12px "IBM Plex Sans", system-ui, sans-serif'; ctx.fillText(subtitle, pad, pad + 34); }
  ctx.drawImage(img, pad, pad + head, rect.width, rect.height);
  URL.revokeObjectURL(url);
  await new Promise<void>((resolve) => canvas.toBlob((b) => { if (b) saveBlob(b, `${slug(name)}.png`); resolve(); }, 'image/png'));
}

export interface CsvColumn { key: string; label: string }

export function exportRowsCsv(rows: Record<string, unknown>[], columns: CsvColumn[], name: string) {
  const esc = (v: unknown) => {
    if (v === null || v === undefined) return '';
    const s = typeof v === 'number' ? String(Math.round(v * 1e6) / 1e6) : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.map((c) => esc(c.label)).join(','), ...rows.map((r) => columns.map((c) => esc(r[c.key])).join(','))];
  saveBlob(new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' }), `${slug(name)}.csv`);
}

export const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'chart';
