export type AppMode = 'DEV_MOCK' | 'CLOUD_API' | 'GPU_SERVER';

export type Language = 'ru' | 'en';

export type ImageOutputFormat = 'webp' | 'jpeg' | 'avif' | 'png';

export type ScreenId =
  | 'catalog'
  | 'pilot_studio'
  | 'storefront_preview'
  | 'landing_builder'
  | 'rich_seo'
  | 'billing'
  | 'settings';

export type TaskStatus =
  | 'PENDING'
  | 'DOWNLOADING'
  | 'ANALYZING'
  | 'GENERATING_BG'
  | 'PILOT_REVIEW'
  | 'BATCH_PROCESSING'
  | 'READY_TO_PUBLISH'
  | 'UPLOADING'
  | 'SUCCESS'
  | 'FAILED';

export type ImportChannel = 'CMS_API' | 'EXCEL_CSV' | 'DIRECT_UPLOAD';

export interface ContentPreservationRules {
  short_description_suffix: string;
  keep_existing_shortcodes: boolean;
  description_before_shortcode: boolean;
  keep_existing_video: boolean;
  description_before_video: boolean;
  output_format?: ImageOutputFormat;
  output_quality?: number;
}

export interface StoreConfig {
  id: number;
  name: string;
  platform: 'woocommerce' | 'shopify' | 'bitrix' | 'opencart' | 'custom_api';
  base_url: string;
  is_active: boolean;
  masked_credentials: Record<string, string>;
  settings: ContentPreservationRules;
}

export interface CanvasLayerItem {
  id: string;
  type: 'badge' | 'title' | 'subtitle' | 'feature_box';
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  bgColor: string;
  textColor: string;
  fontSize: number;
  borderRadius: number;
  fontFamily?: string;
  fontStyle?: 'bold' | 'normal';
  lineHeight?: number;
}


export interface LayoutSchema {
  slideIndex: number;
  slideRole: string;
  backgroundUrl: string;
  productCutoutUrl: string;
  productBBox: { x: number; y: number; width: number; height: number };
  layers: CanvasLayerItem[];
}

export interface ProductSeoData {
  metaTitle: string;
  metaDescription: string;
  slug: string;
  imageAlt: string;
  schemaOrgType: string;
  shortDescription?: string;
  richContentHtml: string;
  videoUrl?: string;
}

export interface ProductItem {
  id: string;
  dbTaskId?: number;
  sku: string;
  name: string;
  category: string;
  price: number;
  currency: string;
  channel: ImportChannel;
  status: TaskStatus;
  errorMessage?: string;
  originalImageUrl: string;
  generatedPreviewUrl: string;
  pilotApproved: boolean;
  slides: LayoutSchema[];
  seo: ProductSeoData;
}

export interface CategorySeoItem {
  id: string;
  name: string;
  productCount: number;
  metaTitle: string;
  metaDescription: string;
  seoText: string;
}

export interface SystemSettings {
  appMode: AppMode;
  activeStoreId?: number;
  cmsConnectorType: 'woocommerce' | 'shopify' | 'bitrix' | 'opencart' | 'custom_api';
  cmsStoreUrl: string;
  cmsConnectionStatus: 'connected' | 'disconnected' | 'error';
  shortDescriptionSuffix?: string;
  outputFormat?: ImageOutputFormat;
  outputQuality?: number;
  maskedApiKeys: {
    visionProvider: string;
    imageGenProvider: string;
    llmCopywriter: string;
  };
  dailyBudgetLimitUsd: number;
  dailySpentUsd: number;
  enableDeepVision: boolean;
  enableAutoCritic: boolean;
}
export interface BatchJobStatus {
  job_id: string;
  pilot_template_id: number | null;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  total_items: number;
  processed_items: number;
  succeeded_count: number;
  failed_count: number;
  progress_percent: number;
  current_sku: string | null;
  cancel_requested: boolean;
  error_summary: string | null;
}

export interface UserAssetItem {
  id: number;
  category: string;
  name: string;
  asset_url: string;
  source_pilot_id?: number | null;
}

export interface SavedPlateStyleItem {
  id: number;
  code: string;
  archetype: string;
  name: string;
  style_passport: {
    bgColor?: string;
    textColor?: string;
    borderRadius?: number;
    fontSize?: number;
    [key: string]: unknown;
  };
}
export type CanvasAspectPreset = '1:1' | '3:4' | '9:16' | '16:9' | 'custom';

export interface BrandLogoConfig {
  url: string;
  position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
  sizePx: number;
  opacity: number;
}
export interface ProductLandingData {
  hero: { headline: string; subheadline: string; image_url: string };
  benefits: Array<{ title: string; desc: string }>;
  specs: Array<{ key: string; value: string }>;
  scenarios: string[];
  faq: Array<{ q: string; a: string }>;
  isolated_html: string;
}
export interface UserProfile {
  id: number;
  email: string;
  full_name: string;
  role: 'admin' | 'user';
  token_balance: number;
  is_active: boolean;
  admin_spent_today: number;
  admin_daily_safety_limit: number | null;
  created_at: string | null;
}

export interface TokenTransactionItem {
  id: number;
  amount: number;
  balance_after: number;
  operation_type: string;
  description: string;
  created_at: string | null;
}

export interface BillingTariffsResponse {
  welcome_bonus: number;
  max_bonus_per_device: number;
  admin_daily_safety_limit: number;
  token_usd_rate: number;
  cost_per_token_usd?: number;
  reserve_warning_ratio?: number;
  packages?: TokenPackageItem[];
  operations: Record<string, { cost: number; title_ru: string; title_en: string }>;
}

export interface TokenPackageItem {
  code: string;
  name_ru: string;
  name_en: string;
  tokens: number;
  price_usd: number;
  currency: string;
  badge_ru: string;
  badge_en: string;
  is_active: boolean;
}

export interface PaymentOrderItem {
  id: number;
  order_uid: string;
  user_id: number;
  provider: string;
  external_payment_id: string | null;
  package_code: string;
  package_name: string;
  tokens_amount: number;
  amount_usd: number;
  currency: string;
  status: 'PENDING' | 'PAID' | 'FAILED';
  checkout_url: string;
  paid_at: string | null;
  created_at: string | null;
}

export interface SolvencyReportResponse {
  health_status: 'HEALTHY' | 'WARNING' | 'CRITICAL';
  is_solvent: boolean;
  alert_message: string;
  cost_per_token_usd: number;
  reserve_warning_ratio: number;
  client_tokens_total: number;
  all_users_tokens_total: number;
  required_reserve_usd: number;
  actual_provider_balance_usd: number;
  deficit_usd: number;
  recommended_topup_usd: number;
  coverage_ratio: number;
  wallets: Array<{
    id: number;
    provider_code: string;
    display_name: string;
    balance_usd: number;
    last_synced_at: string | null;
  }>;
  ledger: Array<{
    id: number;
    provider_code: string;
    entry_type: string;
    amount_usd: number;
    balance_after_usd: number;
    note: string;
    created_at: string | null;
  }>;
}

export interface SupportMessageItem {
  id: number;
  user_id: number;
  sender_role: 'user' | 'admin';
  body: string;
  is_read_by_user: boolean;
  is_read_by_admin: boolean;
  created_at: string | null;
}

export interface SupportThreadSummary {
  user_id: number;
  user_email: string;
  user_name: string;
  unread_count: number;
  last_message: string;
  last_sender_role: 'user' | 'admin';
  last_at: string | null;
}
