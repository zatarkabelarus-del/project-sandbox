import { CategorySeoItem, ProductItem, SystemSettings } from '../types/schema';

// Универсальные нейтральные SVG-заглушки (data URI) для работы оффлайн в контуре DEV_MOCK
const createMockSvg = (label: string, bg: string, accent: string) => {
  const svg = `<svg xmlns="http://w3.org" width="800" height="800" viewBox="0 0 800 800">
    <rect width="800" height="800" fill="${bg}"/>
    <circle cx="400" cy="420" r="210" fill="${accent}" opacity="0.18"/>
    <rect x="270" y="270" width="260" height="300" rx="28" fill="${accent}" opacity="0.85"/>
    <text x="400" y="640" font-family="sans-serif" font-size="24" fill="#334155" text-anchor="middle">${label}</text>
  </svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
};

export const INITIAL_PRODUCTS: ProductItem[] = [
  {
    id: 'prod-001',
    sku: 'SKU-1042',
    name: 'Универсальный модуль управления серии Pro X2',
    category: 'Электронные модули',
    price: 14900,
    currency: 'RUB',
    channel: 'CMS_API',
    status: 'PILOT_REVIEW',
    originalImageUrl: createMockSvg('RAW PHOTO: SKU-1042', '#e2e8f0', '#64748b'),
    generatedPreviewUrl: '',
    pilotApproved: false,
    slides: [],

    seo: {
      metaTitle: 'Универсальный модуль управления серии Pro X2 — купить с гарантией',
      metaDescription:
        'Модуль управления Pro X2 с защитой от перегрузок и быстрым монтажом. Характеристики, совместимость, доставка.',
      slug: 'universal-control-module-pro-x2',
      imageAlt: 'Универсальный модуль управления серии Pro X2 вид спереди',
      schemaOrgType: 'Product',
      richContentHtml: `<div class="ai-rich-block">
  <h3>Ключевые преимущества модели Pro X2</h3>
  <ul>
    <li><strong>Стабильная работа:</strong> встроенная многоуровневая защита от скачков напряжения.</li>
    <li><strong>Простой монтаж:</strong> полная совместимость со штатными разъемами.</li>
  </ul>
</div>`,
    },
  },
  {
    id: 'prod-002',
    sku: 'SKU-1043',
    name: 'Комплект усиленных креплений М8 (набор 4 шт.)',
    category: 'Монтажные комплекты',
    price: 2450,
    currency: 'RUB',
    channel: 'CMS_API',
    status: 'READY_TO_PUBLISH',
    originalImageUrl: createMockSvg('RAW PHOTO: SKU-1043', '#e2e8f0', '#64748b'),
    generatedPreviewUrl: createMockSvg('STUDIO SCENE: SKU-1043', '#ecfdf5', '#059669'),
    pilotApproved: true,
    slides: [],
    seo: {
      metaTitle: 'Комплект усиленных креплений М8 (4 шт.) — антикоррозийное покрытие',
      metaDescription:
        'Набор монтажных креплений М8 повышенной прочности. Устойчивость к вибрации и перепадам температур.',
      slug: 'reinforced-mounting-kit-m8-4pcs',
      imageAlt: 'Комплект усиленных креплений М8 из 4 элементов',
      schemaOrgType: 'Product',
      richContentHtml: `<div class="ai-rich-block">
  <h3>Надежная фиксация в любых условиях</h3>
  <p>Изготовлено из легированной стали с защитным покрытием.</p>
</div>`,
    },
  },
  {
    id: 'prod-003',
    sku: 'SKU-1044',
    name: 'Датчик контроля температуры и давления DT-90',
    category: 'Сенсоры и датчики',
    price: 5800,
    currency: 'RUB',
    channel: 'EXCEL_CSV',
    status: 'BATCH_PROCESSING',
    originalImageUrl: createMockSvg('RAW PHOTO: SKU-1044', '#e2e8f0', '#64748b'),
    generatedPreviewUrl: createMockSvg('PROCESSING: SKU-1044', '#fefce8', '#ca8a04'),
    pilotApproved: true,
    slides: [],
    seo: {
      metaTitle: 'Датчик температуры и давления DT-90 — высокая точность измерений',
      metaDescription: 'Цифровой датчик DT-90 для непрерывного мониторинга рабочих параметров.',
      slug: 'temperature-pressure-sensor-dt-90',
      imageAlt: 'Датчик контроля температуры и давления DT-90',
      schemaOrgType: 'Product',
      richContentHtml: '<div class="ai-rich-block"><p>Точность измерений до 0.1%.</p></div>',
    },
  },
  {
    id: 'prod-004',
    sku: 'SKU-1045',
    name: 'Блок питания стабилизированный 24V 5A',
    category: 'Электропитание',
    price: 4100,
    currency: 'RUB',
    channel: 'DIRECT_UPLOAD',
    status: 'FAILED',
    errorMessage: 'InvalidMediaError: Исходное разрешение изображения ниже 400x400 px',
    originalImageUrl: createMockSvg('LOW RES PHOTO', '#fee2e2', '#dc2626'),
    generatedPreviewUrl: createMockSvg('ERROR', '#fee2e2', '#dc2626'),
    pilotApproved: false,
    slides: [],
    seo: {
      metaTitle: 'Стабилизированный блок питания 24V 5A',
      metaDescription: 'Компактный импульсный блок питания 24 Вольта 5 Ампер.',
      slug: 'power-supply-24v-5a',
      imageAlt: 'Блок питания 24V 5A',
      schemaOrgType: 'Product',
      richContentHtml: '<div class="ai-rich-block"><p>Защита от короткого замыкания.</p></div>',
    },
  },
];

export const INITIAL_CATEGORIES: CategorySeoItem[] = [
  {
    id: 'cat-01',
    name: 'Электронные модули',
    productCount: 142,
    metaTitle: 'Электронные модули управления — каталог, цены, подбор',
    metaDescription:
      'Широкий ассортимент электронных модулей управления с гарантией качества и быстрой доставкой.',
    seoText:
      'В разделе представлены современные модули управления для промышленного и бытового применения. Все позиции проходят предпродажную проверку.',
  },
  {
    id: 'cat-02',
    name: 'Сенсоры и датчики',
    productCount: 89,
    metaTitle: 'Сенсоры и промышленные датчики — купить онлайн',
    metaDescription:
      'Датчики температуры, давления и положения от проверенных производителей.',
    seoText:
      'Подберите высокоточные датчики для автоматизации и контроля технологических процессов.',
  },
];

export const INITIAL_SETTINGS: SystemSettings = {
  appMode: 'DEV_MOCK',
  cmsConnectorType: 'woocommerce',
  cmsStoreUrl: 'https://example-store.local',
  cmsConnectionStatus: 'connected',
  maskedApiKeys: {
    visionProvider: 'sk-vis-••••••••••••••••••••9a4f',
    imageGenProvider: 'sk-img-••••••••••••••••••••3c1e',
    llmCopywriter: 'sk-llm-••••••••••••••••••••7b8d',
  },
  dailyBudgetLimitUsd: 25.0,
  dailySpentUsd: 3.42,
  enableDeepVision: true,
  enableAutoCritic: true,
};
