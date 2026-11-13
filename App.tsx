import React, { useState } from 'react';
import {
  Layers,
  Palette,
  Store,
  FileText,
  Settings,
  Globe,
  Cpu,
} from 'lucide-react';
import { LanguageProvider, useTranslation } from './i18n/LanguageContext';
import {
  INITIAL_CATEGORIES,
  INITIAL_PRODUCTS,
  INITIAL_SETTINGS,
} from './data/mockData';
import {
  CategorySeoItem,
  ProductItem,
  ScreenId,
  SystemSettings,
} from './types/schema';
import { CatalogManager } from './components/CatalogManager/CatalogManager';
import { PilotEditor } from './components/PilotEditor/PilotEditor';
import { StorefrontPreview } from './components/StorefrontPreview/StorefrontPreview';
import { SeoDashboard } from './components/SeoDashboard/SeoDashboard';
import { SettingsPanel } from './components/Settings/SettingsPanel';

const MainShell: React.FC = () => {
  const { lang, setLang, t } = useTranslation();
  const [activeScreen, setActiveScreen] = useState<ScreenId>('catalog');
  const [products, setProducts] = useState<ProductItem[]>(INITIAL_PRODUCTS);
  const [categories, setCategories] = useState<CategorySeoItem[]>(INITIAL_CATEGORIES);
  const [settings, setSettings] = useState<SystemSettings>(INITIAL_SETTINGS);
  const [selectedProductId, setSelectedProductId] = useState<string>(INITIAL_PRODUCTS[0].id);

  const activeProduct =
    products.find((p) => p.id === selectedProductId) || products[0];

  const handleOpenPilot = (product: ProductItem) => {
    setSelectedProductId(product.id);
    setActiveScreen('pilot_studio');
  };

  const handleApprovePilot = (productId: string, updated: ProductItem) => {
    setProducts((prev) => prev.map((p) => (p.id === productId ? updated : p)));
  };

  const handleRunBatch = () => {
    setProducts((prev) =>
      prev.map((p) =>
        p.pilotApproved && p.status !== 'FAILED'
          ? { ...p, status: 'SUCCESS' }
          : p
      )
    );
  };

  const handleDirectUpload = (file: File) => {
    const objectUrl = URL.createObjectURL(file);
    const newProduct: ProductItem = {
      id: `prod-${Date.now()}`,
      sku: `TEST-${Math.floor(1000 + Math.random() * 9000)}`,
      name: file.name.replace(/\.[^/.]+$/, ''),
      category: 'Экспресс-тест (Загрузка)',
      price: 9900,
      currency: 'RUB',
      channel: 'DIRECT_UPLOAD',
      status: 'PILOT_REVIEW',
      originalImageUrl: objectUrl,
      generatedPreviewUrl: objectUrl,
      pilotApproved: false,
      slides: [],
      seo: {
        metaTitle: `${file.name} — SEO заголовок`,
        metaDescription: 'Автоматически сгенерированное описание товара.',
        slug: `item-${Date.now()}`,
        imageAlt: file.name,
        schemaOrgType: 'Product',
        richContentHtml: '<div class="ai-rich-block"><p>Демонстрационный рич-контент.</p></div>',
      },
    };
    setProducts((prev) => [newProduct, ...prev]);
    setSelectedProductId(newProduct.id);
    setActiveScreen('pilot_studio');
  };

  const handleSyncCms = () => {
    const syncedItem: ProductItem = {
      id: `prod-cms-${Date.now()}`,
      sku: `CMS-${Math.floor(2000 + Math.random() * 7000)}`,
      name: 'Новый товар из CMS REST API',
      category: 'Синхронизированный раздел',
      price: 7500,
      currency: 'RUB',
      channel: 'CMS_API',
      status: 'PILOT_REVIEW',
      originalImageUrl: INITIAL_PRODUCTS[0].originalImageUrl,
      generatedPreviewUrl: INITIAL_PRODUCTS[0].generatedPreviewUrl,
      pilotApproved: false,
      slides: INITIAL_PRODUCTS[0].slides,
      seo: INITIAL_PRODUCTS[0].seo,
    };
    setProducts((prev) => [syncedItem, ...prev]);
  };

  const handleImportCsv = () => {
    const csvItem: ProductItem = {
      id: `prod-csv-${Date.now()}`,
      sku: `CSV-${Math.floor(3000 + Math.random() * 6000)}`,
      name: 'Позиция из прайс-листа (строка #14)',
      category: 'Импорт Excel/CSV',
      price: 3200,
      currency: 'RUB',
      channel: 'EXCEL_CSV',
      status: 'PENDING',
      originalImageUrl: INITIAL_PRODUCTS[0].originalImageUrl,
      generatedPreviewUrl: INITIAL_PRODUCTS[0].generatedPreviewUrl,
      pilotApproved: false,
      slides: [],
      seo: INITIAL_PRODUCTS[0].seo,
    };
    setProducts((prev) => [csvItem, ...prev]);
  };

  const navItems: { id: ScreenId; label: string; icon: React.ReactNode }[] = [
    { id: 'catalog', label: t('nav.catalog'), icon: <Layers className="w-4 h-4" /> },
    { id: 'pilot_studio', label: t('nav.pilot_studio'), icon: <Palette className="w-4 h-4" /> },
    { id: 'storefront_preview', label: t('nav.storefront_preview'), icon: <Store className="w-4 h-4" /> },
    { id: 'rich_seo', label: t('nav.rich_seo'), icon: <FileText className="w-4 h-4" /> },
    { id: 'settings', label: t('nav.settings'), icon: <Settings className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen flex bg-slate-50 text-slate-900">
      <aside className="w-64 bg-slate-900 text-slate-100 flex flex-col justify-between shrink-0">
        <div>
          <div className="p-5 border-b border-slate-800">
            <div className="font-bold text-lg tracking-tight text-white">
              {t('app.title')}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">{t('app.subtitle')}</div>
          </div>

          <nav className="p-3 space-y-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveScreen(item.id)}
                className={`w-full flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition cursor-pointer ${
                  activeScreen === item.id
                    ? 'bg-blue-600 text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                {item.icon}
                {item.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-4 border-t border-slate-800 space-y-3 text-xs">
          <div className="flex items-center justify-between bg-slate-800/80 px-3 py-2 rounded-lg">
            <span className="flex items-center gap-1.5 text-slate-400">
              <Cpu className="w-3.5 h-3.5 text-emerald-400" />
              {t('app.mode_label')}:
            </span>
            <span className="font-mono font-bold text-emerald-400">{settings.appMode}</span>
          </div>

          <div className="flex items-center justify-between bg-slate-800/80 px-3 py-2 rounded-lg">
            <span className="flex items-center gap-1.5 text-slate-400">
              <Globe className="w-3.5 h-3.5 text-blue-400" />
              Язык / Lang:
            </span>
            <div className="inline-flex rounded bg-slate-900 p-0.5">
              <button
                onClick={() => setLang('ru')}
                className={`px-2 py-0.5 rounded font-semibold cursor-pointer ${
                  lang === 'ru' ? 'bg-blue-600 text-white' : 'text-slate-400'
                }`}
              >
                RU
              </button>
              <button
                onClick={() => setLang('en')}
                className={`px-2 py-0.5 rounded font-semibold cursor-pointer ${
                  lang === 'en' ? 'bg-blue-600 text-white' : 'text-slate-400'
                }`}
              >
                EN
              </button>
            </div>
          </div>
        </div>
      </aside>

      <main className="flex-1 p-6 lg:p-8 overflow-y-auto">
        {activeScreen === 'catalog' && (
          <CatalogManager
            products={products}
            onSelectForPilot={handleOpenPilot}
            onRunBatch={handleRunBatch}
            onDirectUpload={handleDirectUpload}
            onSyncCms={handleSyncCms}
            onImportCsv={handleImportCsv}
          />
        )}

        {activeScreen === 'pilot_studio' && (
          <PilotEditor product={activeProduct} onApprovePilot={handleApprovePilot} />
        )}

        {activeScreen === 'storefront_preview' && (
          <StorefrontPreview
            products={products}
            activeProduct={activeProduct}
            onSelectProduct={(p) => setSelectedProductId(p.id)}
          />
        )}

        {activeScreen === 'rich_seo' && (
          <SeoDashboard
            products={products}
            settings={settings}
            onUpdateProduct={(updated) =>
              setProducts((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
            }
          />
        )}

        {activeScreen === 'settings' && (
          <SettingsPanel
            settings={settings}
            onUpdateSettings={(patch) => setSettings((prev) => ({ ...prev, ...patch }))}
          />
        )}
      </main>
    </div>
  );
};

export const App: React.FC = () => (
  <LanguageProvider>
    <MainShell />
  </LanguageProvider>
);

export default App;
