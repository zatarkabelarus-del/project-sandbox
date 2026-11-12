const API_BASE_URL =
  (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_URL ||
  'http://127.0.0';

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

  runPilotPreview: (payload: {
    product_id: string;
    title: string;
    image_url?: string;
    category?: string;
    style_archetype?: string;
    generation_mode?: string;
    enable_vision?: boolean;
    slides_count?: number;
    lang?: string;
  }) =>
    requestJson<Record<string, unknown>>('/pilot/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  approvePilotTemplate: (payload: {
    name: string;
    pilot_product_id: number;
    style_code: string;
    approved_layout_schema: Record<string, unknown>;
    scene_mode?: string;
    enable_vision?: boolean;
  }) =>
    requestJson<{ pilot_template_id: number; is_approved: boolean }>('/pilot/approve', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  runBatchSeries: (payload: { pilot_template_id: number; product_ids: number[]; lang?: string }) =>
    requestJson<{ pilot_template_id: number; batch_summary: Record<string, unknown> }>('/batch/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  publishToWooCommerce: (payload: {
    task_id: number;
    store_url?: string;
    consumer_key?: string;
    consumer_secret?: string;
    bridge_token?: string;
    external_product_id?: string;
    preview_only?: boolean;
    lang?: string;
  }) =>
    requestJson<Record<string, unknown>>('/publish/woocommerce', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
