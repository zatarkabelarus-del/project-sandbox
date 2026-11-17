import {
  BatchJobStatus,
  BillingTariffsResponse,
  ProductLandingData,
  SavedPlateStyleItem,
  StoreConfig,
  TokenTransactionItem,
  UserAssetItem,
  UserProfile,
} from '../types/schema';

const API_BASE_URL =
  (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_URL ||
  'http://127.0.0';

const TOKEN_STORAGE_KEY = 'ai_picchanger_jwt_token';
const DEVICE_FP_KEY = 'ai_picchanger_device_fp';

export const authStorage = {
  getToken: (): string => localStorage.getItem(TOKEN_STORAGE_KEY) || '',
  setToken: (token: string): void => localStorage.setItem(TOKEN_STORAGE_KEY, token),
  clearToken: (): void => localStorage.removeItem(TOKEN_STORAGE_KEY),
};

export function getDeviceFingerprint(): string {
  let cached = localStorage.getItem(DEVICE_FP_KEY);
  if (cached) return cached;
  const raw = [
    navigator.userAgent,
    navigator.language,
    `${screen.width}x${screen.height}x${screen.colorDepth}`,
    Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    String(navigator.hardwareConcurrency || 4),
  ].join('|');
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i += 1) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  cached = `dev-${(hash >>> 0).toString(16).padStart(8, '0')}`;
  localStorage.setItem(DEVICE_FP_KEY, cached);
  return cached;
}

function buildSecurityHeaders(extra?: HeadersInit): Record<string, string> {
  const headers: Record<string, string> = {
    'X-Device-Fingerprint': getDeviceFingerprint(),
    ...((extra as Record<string, string>) || {}),
  };
  const token = authStorage.getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: buildSecurityHeaders({
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    }),
  });
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.localized_message || errBody.message || errBody.detail || `HTTP ${response.status}`);
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

  registerUser: (payload: { email: string; password: string; full_name?: string }) =>
    requestJson<{ access_token: string; bonus_granted: boolean; user: UserProfile }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  loginUser: (payload: { email: string; password: string }) =>
    requestJson<{ access_token: string; user: UserProfile }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getMyProfile: () => requestJson<{ user: UserProfile }>('/auth/me'),

  updateMyProfile: (payload: {
    current_password: string;
    new_email?: string;
    full_name?: string;
    new_password?: string;
  }) =>
    requestJson<{ user: UserProfile }>('/auth/profile', {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  getBillingTariffs: () => requestJson<BillingTariffsResponse>('/billing/tariffs'),

  getBillingTransactions: (limit: number = 30) =>
    requestJson<{ balance: number; role: string; items: TokenTransactionItem[] }>(
      `/billing/transactions?limit=${limit}`
    ),

  adminListUsers: () => requestJson<{ users: UserProfile[] }>('/billing/admin/users'),

  adminAdjustUser: (payload: {
    target_user_id: number;
    delta_tokens?: number;
    new_role?: 'admin' | 'user';
    reason?: string;
  }) =>
    requestJson<{ user: UserProfile }>('/billing/admin/adjust', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

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
      headers: buildSecurityHeaders(),
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

  getMyBackgrounds: () =>
    requestJson<{ items: UserAssetItem[] }>('/assets/my-backgrounds'),

  getMyPlates: () =>
    requestJson<{ items: SavedPlateStyleItem[] }>('/styles/my-plates'),

  removeProductBackground: (imageUrl: string) =>
    requestJson<{ cutout_data_url: string; engine: string; tokens_spent: number }>(
      `/graphics/remove-bg?image_url=${encodeURIComponent(imageUrl)}`,
      { method: 'POST' }
    ),

  uploadCustomBackground: async (file: File): Promise<UserAssetItem> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch(`${API_BASE_URL}/assets/upload-background`, {
      method: 'POST',
      headers: buildSecurityHeaders(),
      body: formData,
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json() as Promise<UserAssetItem>;
  },

  runBatchSeries: (payload: {
    pilot_template_id: number;
    product_ids: number[];
    lang?: string;
    async_mode?: boolean;
  }) =>
    requestJson<{
      job_id: string;
      status?: string;
      total_items?: number;
      pilot_template_id: number;
      batch_summary?: Record<string, unknown>;
    }>('/batch/run', {
      method: 'POST',
      body: JSON.stringify({ async_mode: true, ...payload }),
    }),

  getBatchJobStatus: (jobId: string) =>
    requestJson<BatchJobStatus>(`/batch/status/${encodeURIComponent(jobId)}`),

  getActiveBatchJob: () =>
    requestJson<{ job: BatchJobStatus | null }>('/batch/active'),

  cancelBatchJob: (jobId: string) =>
    requestJson<BatchJobStatus>(`/batch/cancel/${encodeURIComponent(jobId)}`, {
      method: 'POST',
    }),

  publishToWooCommerce: (payload: {
    task_id: number;
    store_id?: number;
    output_format?: 'webp' | 'jpeg' | 'avif' | 'png';
    output_quality?: number;
    preview_only?: boolean;
    lang?: string;
    [key: string]: unknown;
  }) =>
    requestJson<Record<string, unknown>>('/publish/woocommerce', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  generateProductLanding: (payload: {
    sku: string;
    title: string;
    category?: string;
    price?: number;
    attributes?: Record<string, unknown>;
    image_url?: string;
    theme?: string;
    lang?: string;
  }) =>
    requestJson<ProductLandingData>('/landing/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
