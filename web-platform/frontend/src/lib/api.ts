import type {
  Capabilities, DatasetDetail, DatasetSummary, FilterOptions, Filters, SheetAnalysis, UploadResult,
} from './types';

const BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function parseError(res: Response): Promise<ApiError> {
  let msg = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (typeof body.detail === 'string') msg = body.detail;
    else if (Array.isArray(body.detail)) msg = body.detail.map((d: { msg: string }) => d.msg).join('; ');
  } catch { /* non-JSON error body */ }
  return new ApiError(res.status, msg);
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body: unknown, signal?: AbortSignal) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body), signal });

/** Strip empty arrays / nulls so requests stay small and cache keys stable. */
export function compactFilters(f: Filters): Partial<Filters> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(f)) {
    if (v === null || v === undefined) continue;
    if (Array.isArray(v) && v.length === 0) continue;
    out[k] = v;
  }
  return out as Partial<Filters>;
}

export type Module =
  | 'overview' | 'kpis' | 'performance' | 'products' | 'regional' | 'customers' | 'financial'
  | 'operations' | 'forecast' | 'insights' | 'breakdown' | 'timeseries';

export interface AnalyticsParams {
  granularity?: string; dimension?: string; split_by?: string; sort_by?: string; limit?: number;
  ascending?: boolean; horizon?: number; use_ai?: boolean;
}

export const api = {
  health: () => request<{ status: string; database: string; time: string }>('/api/health'),
  systemInfo: () => request<{ name: string; version: string; environment: string; max_upload_mb: number;
    ai_insights: { enabled: boolean; configured: boolean; model: string } }>('/api/system/info'),
  datasets: () => request<DatasetSummary[]>('/api/datasets'),
  dataset: (id: number) => request<DatasetDetail>(`/api/datasets/${id}`),
  patchDataset: (id: number, body: { name?: string; is_default?: boolean }) =>
    request<DatasetSummary>(`/api/datasets/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteDataset: (id: number) => request<void>(`/api/datasets/${id}`, { method: 'DELETE' }),
  capabilities: (id: number) => request<Capabilities>(`/api/datasets/${id}/capabilities`),
  filterOptions: (id: number) => request<FilterOptions>(`/api/datasets/${id}/filter-options`),
  search: (id: number, q: string, signal?: AbortSignal) =>
    request<{ dimension: string; label: string; value: string; revenue: number }[]>(
      `/api/datasets/${id}/search?q=${encodeURIComponent(q)}`, { signal }),
  analytics: <T,>(id: number, module: Module, filters: Filters, params: AnalyticsParams = {}, signal?: AbortSignal) =>
    post<T>(`/api/datasets/${id}/analytics/${module}`, { filters: compactFilters(filters), ...params }, signal),
  records: <T,>(id: number, body: unknown, signal?: AbortSignal) => post<T>(`/api/datasets/${id}/records/query`, body, signal),
  record: <T,>(id: number, recordId: number) => request<T>(`/api/datasets/${id}/records/${recordId}`),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<UploadResult>('/api/uploads', { method: 'POST', body: fd });
  },
  analyzeSheet: (uploadId: string, sheet: string | null, headerRow?: number | null) => {
    const q = new URLSearchParams();
    if (sheet) q.set('sheet', sheet);
    if (headerRow !== undefined && headerRow !== null) q.set('header_row', String(headerRow));
    return request<SheetAnalysis>(`/api/uploads/${uploadId}/analysis?${q}`);
  },
  createDataset: (body: unknown) => post<DatasetDetail>('/api/datasets', body),
  presets: (datasetId?: number) =>
    request<Preset[]>(`/api/presets${datasetId ? `?dataset_id=${datasetId}` : ''}`),
  savePreset: (body: { name: string; dataset_id: number | null; filters: Partial<Filters>; is_default?: boolean }) =>
    post<Preset>('/api/presets', body),
  deletePreset: (id: number) => request<void>(`/api/presets/${id}`, { method: 'DELETE' }),
};

export interface Preset { id: number; name: string; dataset_id: number | null; filters: Partial<Filters>; is_default: boolean; created_at: string }

/** POST and save the response as a file (exports and reports). */
export async function downloadPost(path: string, body: unknown, fallbackName: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) throw await parseError(res);
  const cd = res.headers.get('Content-Disposition') ?? '';
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const blob = await res.blob();
  saveBlob(blob, name);
}

export async function openHtmlReport(path: string, body: unknown): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) throw await parseError(res);
  const html = await res.text();
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
  window.open(url, '_blank', 'noopener');
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
