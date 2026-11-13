import { StoreConfig } from '../types/schema';

const API_BASE_URL =
  (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_URL ||
  'http://127.0.0.1:8000/api';

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.localized_message || errBody.detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export interface TableImportReport {
  total_rows: number;
  valid_count: number;
  error_count: number;
  created_product_ids: number[];
  errors: Array<{ row: number; field?: string; message: string }>;
}

export const apiClient = {
  getHealth: (lang: string = 'ru') =>
    requestJson<{
      status: string;
      app_mode: string;
      provider: string;
      budget?: { daily_limit_usd: number; spent_today_usd: number; remaining_usd: number };
    }>(`/health?lang=${lang}`),

  getStyles: () => requestJson<{ styles: Array<Record<string, unknown>> }>('/styles'),

  maskSecret: (secretValue: string) =>
    requestJson<{ stored_encrypted: boolean; masked_preview: string }>('/security/mask-secret', {
      method: 'POST',
      body: JSON.stringify({ secret_value: secretValue }),
    }),

  listStores: () => requestJson<{ stores: StoreConfig[] }>('/stores'),

  createStore: (payload: {
    name: string;
    platform: string;
    base_url: string;
    consumer_key?: string;
    consumer_secret?: string;
    bridge_token?: string;
    settings?: Record<string, unknown>;
  }) =>
    requestJson<{ store: StoreConfig }>('/stores', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updateStore: (
    storeId: number,
    payload: {
      name: string;
      platform: string;
      base_url: string;
      consumer_key?: string;
      consumer_secret?: string;
      bridge_token?: string;
      settings?: Record<string, unknown>;
    }
  ) =>
    requestJson<{ store: StoreConfig }>(`/stores/${storeId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  checkStoreConnection: (storeId: number) =>
    requestJson<{ store_id: number; connected: boolean; mode: string }>(
      `/stores/${storeId}/check-connection`,
      { method: 'POST' }
    ),

  syncWooCommerceCatalog: (payload: { store_id: number; page?: number; per_page?: number }) =>
    requestJson<{ store_id: number; synced_count: number; product_ids: number[] }>(
      '/catalog/sync-woocommerce',
      { method: 'POST', body: JSON.stringify(payload) }
    ),

  getStoreCategories: (storeId: number) =>
    requestJson<{
      store_id: number;
      categories: Array<{ external_id: string; name: string; slug: string; count: number }>;
    }>(`/seo/categories?store_id=${storeId}`),

  generateCategoriesSeo: (payload: {
    categories: Array<{ external_id: string; name: string; count: number }>;
    lang?: string;
  }) =>
    requestJson<{
      items: Array<{
        external_id: string;
        name: string;
        meta_title: string;
        meta_description: string;
        seo_text: string;
      }>;
    }>('/seo/categories/generate', { method: 'POST', body: JSON.stringify(payload) }),

  publishCategorySeo: (payload: {
    store_id: number;
    external_category_id: string;
    seo_text: string;
    meta_title: string;
    meta_description: string;
    preview_only?: boolean;
  }) =>
    requestJson<Record<string, unknown>>('/seo/categories/publish', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  importCatalogTable: async (file: File): Promise<TableImportReport> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`${API_BASE_URL}/catalog/import-table`, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      throw new Error(errBody.localized_message || errBody.detail || `HTTP ${response.status}`);
    }
    return response.json() as Promise<TableImportReport>;
  },

  runPilotPreview: (payload: Record<string, unknown>) =>
    requestJson<Record<string, unknown>>('/pilot/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  approvePilotTemplate: (payload: Record<string, unknown>) =>
    requestJson<{ pilot_template_id: number; is_approved: boolean }>('/pilot/approve', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  runBatchSeries: (payload: { pilot_template_id: number; product_ids: number[]; lang?: string }) =>
    requestJson<{ pilot_template_id: number; batch_summary: Record<string, unknown> }>('/batch/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  publishToWooCommerce: (payload: Record<string, unknown>) =>
    requestJson<Record<string, unknown>>('/publish/woocommerce', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
