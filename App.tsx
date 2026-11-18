import React, { useEffect, useState } from 'react';
import {
  Coins,
  Cpu,
  FileText,
  Globe,
  Layers,
  LayoutTemplate,
  LogIn,
  LogOut,
  Palette,
  Settings,
  Store,
} from 'lucide-react';
import { apiClient, authStorage } from './api/client';
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
  UserProfile,
} from './types/schema';
import { AuthModal } from './components/Auth/AuthModal';
import { BillingPanel } from './components/Billing/BillingPanel';
import { CatalogManager } from './components/CatalogManager/CatalogManager';
import { PilotEditor } from './components/PilotEditor/PilotEditor';
import { StorefrontPreview } from './components/StorefrontPreview/StorefrontPreview';
import { LandingBuilder } from './components/LandingBuilder/LandingBuilder';
import { SeoDashboard } from './components/SeoDashboard/SeoDashboard';
import { SettingsPanel } from './components/Settings/SettingsPanel';

const MainShell: React.FC = () => {
  const { lang, setLang, t } = useTranslation();
  const [activeScreen, setActiveScreen] = useState<ScreenId>('catalog');
  const [products, setProducts] = useState<ProductItem[]>(INITIAL_PRODUCTS);
  const [categories] = useState<CategorySeoItem[]>(INITIAL_CATEGORIES);
  const [settings, setSettings] = useState<SystemSettings>(INITIAL_SETTINGS);
  const [selectedProductId, setSelectedProductId] = useState<string>(INITIAL_PRODUCTS.at(0)!.id);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [isAuthOpen, setIsAuthOpen] = useState<boolean>(false);
  const [authNotice, setAuthNotice] = useState<string>('');

  const refreshProfile = async () => {
    if (!authStorage.getToken()) {
      setCurrentUser(null);
      return;
    }
    try {
      const res = await apiClient.getMyProfile();
      setCurrentUser(res.user);
    } catch {
      authStorage.clearToken();
      setCurrentUser(null);
    }
  };

  useEffect(() => {
    refreshProfile();
  }, []);

  const handleLogout = () => {
    authStorage.clearToken();
    setCurrentUser(null);
    setAuthNotice('');
  };

  const activeProduct =
    products.find((p) => p.id === selectedProductId) || products.at(0)!;

  const handleOpenPilot = (product: ProductItem) => {
    setSelectedProductId(product.id);
    setActiveScreen('pilot_studio');
  };

  const handleApprovePilot = (productId: string, updated: ProductItem) => {
    setProducts((prev) => prev.map((p) => (p.id === productId ? updated : p)));
    refreshProfile();
  };

  const handleRunBatch = () => {
    setProducts((prev) =>
      prev.map((p) =>
        p.pilotApproved && p.status !== 'FAILED'
          ? { ...p, status: 'SUCCESS' }
          : p
      )
    );
    refreshProfile();
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
    const baseItem = INITIAL_PRODUCTS.at(0)!;
    const syncedItem: ProductItem = {
      id: `prod-cms-${Date.now()}`,
      sku: `CMS-${Math.floor(2000 + Math.random() * 7000)}`,
      name: 'Новый товар из CMS REST API',
      category: 'Синхронизированный раздел',
      price: 7500,
      currency: 'RUB',
      channel: 'CMS_API',
      status: 'PILOT_REVIEW',
      originalImageUrl: baseItem.originalImageUrl,
      generatedPreviewUrl: baseItem.generatedPreviewUrl,
      pilotApproved: false,
      slides: baseItem.slides,
      seo: baseItem.seo,
    };
    setProducts((prev) => [syncedItem, ...prev]);
  };

  const handleImportCsv = () => {
    const baseItem = INITIAL_PRODUCTS.at(0)!;
    const csvItem: ProductItem = {
      id: `prod-csv-${Date.now()}`,
      sku: `CSV-${Math.floor(3000 + Math.random() * 6000)}`,
      name: 'Позиция из прайс-листа (строка #14)',
      category: 'Импорт Excel/CSV',
      price: 3200,
      currency: 'RUB',
      channel: 'EXCEL_CSV',
      status: 'PENDING',
      originalImageUrl: baseItem.originalImageUrl,
      generatedPreviewUrl: baseItem.generatedPreviewUrl,
      pilotApproved: false,
      slides: [],
      seo: baseItem.seo,
    };
    setProducts((prev) => [csvItem, ...prev]);
  };

  const navItems: { id: ScreenId; label: string; icon: React.ReactNode }[] = [
    { id: 'catalog', label: t('nav.catalog'), icon: <Layers className="w-4 h-4" /> },
    { id: 'pilot_studio', label: t('nav.pilot_studio'), icon: <Palette className="w-4 h-4" /> },
    { id: 'storefront_preview', label: t('nav.storefront_preview'), icon: <Store className="w-4 h-4" /> },
    { id: 'landing_builder', label: t('nav.landing_builder'), icon: <LayoutTemplate className="w-4 h-4" /> },
    { id: 'rich_seo', label: t('nav.rich_seo'), icon: <FileText className="w-4 h-4" /> },
    { id: 'billing', label: lang === 'ru' ? 'Баланс и аккаунт' : 'Billing & Account', icon: <Coins className="w-4 h-4" /> },
    { id: 'settings', label: t('nav.settings'), icon: <Settings className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen flex bg-slate-50 text-slate-900">
      <aside className="w-64 bg-slate-900 text-slate-100 flex flex-col justify-between shrink-0">
        <div>
          <div className="p-5 border-b border-slate-800">
            <div className="font-bold text-lg tracking-tight text-white">{t('app.title')}</div>
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

        <div className="p-4 border-t border-slate-800 space-y-2.5 text-xs">
          {currentUser ? (
            <div className="bg-slate-800/90 p-3 rounded-lg space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-white truncate">{currentUser.email}</span>
                <button onClick={handleLogout} title="Выйти" className="text-slate-400 hover:text-rose-400 cursor-pointer">
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
              <button
                onClick={() => setActiveScreen('billing')}
                className="w-full flex items-center justify-between bg-slate-900 px-2.5 py-1.5 rounded text-amber-400 font-bold cursor-pointer"
              >
                <span className="flex items-center gap-1"><Coins className="w-3.5 h-3.5" /> Токены:</span>
                <span>{currentUser.role === 'admin' ? '∞ ADMIN' : currentUser.token_balance}</span>
              </button>
            </div>
          ) : (
            <button
              onClick={() => setIsAuthOpen(true)}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2 px-3 rounded-lg transition cursor-pointer"
            >
              <LogIn className="w-3.5 h-3.5" />
              {lang === 'ru' ? 'Войти / +100 токенов' : 'Sign In / +100 tokens'}
            </button>
          )}

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
                className={`px-2 py-0.5 rounded font-semibold cursor-pointer ${lang === 'ru' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}
              >
                RU
              </button>
              <button
                onClick={() => setLang('en')}
                className={`px-2 py-0.5 rounded font-semibold cursor-pointer ${lang === 'en' ? 'bg-blue-600 text-white' : 'text-slate-400'}`}
              >
                EN
              </button>
            </div>
          </div>
        </div>
      </aside>

      <main className="flex-1 p-6 lg:p-8 overflow-y-auto space-y-4">
        {authNotice && (
          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-900 flex items-center justify-between">
            <span>{authNotice}</span>
            <button onClick={() => setAuthNotice('')} className="text-xs font-bold underline cursor-pointer">OK</button>
          </div>
        )}

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
          <PilotEditor
            product={activeProduct}
            defaultFormat={settings.outputFormat}
            defaultQuality={settings.outputQuality}
            onApprovePilot={handleApprovePilot}
          />
        )}

        {activeScreen === 'storefront_preview' && (
          <StorefrontPreview
            products={products}
            activeProduct={activeProduct}
            onSelectProduct={(p) => setSelectedProductId(p.id)}
          />
        )}

        {activeScreen === 'landing_builder' && (
          <LandingBuilder
            products={products}
            activeProduct={activeProduct}
            onSelectProduct={(p) => setSelectedProductId(p.id)}
            onApplyToRichContent={(productId, html) =>
              setProducts((prev) =>
                prev.map((p) => (p.id === productId ? { ...p, seo: { ...p.seo, richContentHtml: html } } : p))
              )
            }
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

        {activeScreen === 'billing' && (
          <BillingPanel
            currentUser={currentUser}
            onUserUpdated={(u) => setCurrentUser(u)}
            onOpenAuth={() => setIsAuthOpen(true)}
          />
        )}

        {activeScreen === 'settings' && (
          <SettingsPanel
            settings={settings}
            onUpdateSettings={(patch) => setSettings((prev) => ({ ...prev, ...patch }))}
          />
        )}
      </main>

      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        onSuccess={(u, notice) => {
          setCurrentUser(u);
          if (notice) setAuthNotice(notice);
        }}
      />
    </div>
  );
};

export const App: React.FC = () => (
  <LanguageProvider>
    <MainShell />
  </LanguageProvider>
);

export default App;
