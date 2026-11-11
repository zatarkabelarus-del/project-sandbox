const API_BASE_URL = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_URL || "http://127.0.0";

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.localized_message || errBody.detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const apiClient = {
  getHealth: (lang: string = "ru") =>
    requestJson<{ status: string; app_mode: string; provider: string }>(`/health?lang=${lang}`),

  getStyles: () =>
    requestJson<{ styles: Array<Record<string, unknown>> }>("/styles"),

  maskSecret: (secretValue: string) =>
    requestJson<{ stored_encrypted: boolean; masked_preview: string }>("/security/mask-secret", {
      method: "POST",
      body: JSON.stringify({ secret_value: secretValue }),
    }),

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
    requestJson<Record<string, unknown>>("/pilot/preview", {
      method: "POST",
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
    requestJson<{ pilot_template_id: number; is_approved: boolean }>("/pilot/approve", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  runBatchSeries: (payload: { pilot_template_id: number; product_ids: number[]; lang?: string }) =>
    requestJson<{ pilot_template_id: number; batch_summary: Record<string, unknown> }>("/batch/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
