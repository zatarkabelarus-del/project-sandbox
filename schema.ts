export type AppMode = 'DEV_MOCK' | 'CLOUD_API' | 'GPU_SERVER';

export type Language = 'ru' | 'en';

export type ScreenId =
  | 'catalog'
  | 'pilot_studio'
  | 'storefront_preview'
  | 'rich_seo'
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
