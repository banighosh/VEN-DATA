import { api, compactFilters, type AnalyticsParams, type Module } from './api';
import { useAsync } from './hooks';
import { useApp } from '../state/AppState';

/** Fetch an analytics module for the active dataset + global filters. Refetches when either changes. */
export function useModule<T>(module: Module, params: AnalyticsParams = {}, enabled = true) {
  const { dataset, filters, caps } = useApp();
  const key = JSON.stringify([compactFilters(filters), params]);
  return useAsync<T>((signal) => api.analytics<T>(dataset!.id, module, filters, params, signal),
    [dataset?.id, dataset?.updated_at, key], enabled && !!dataset && !!caps);
}
