import React, { useEffect, useState } from 'react';
import { ShieldCheck, Server, DollarSign, Cpu, KeyRound, RefreshCw, CheckCircle2, Plus } from 'lucide-react';
import { StoreConfig, SystemSettings } from '../../types/schema';
import { useTranslation } from '../../i18n/LanguageContext';
import { apiClient } from '../../api/client';

interface SettingsPanelProps {
  settings: SystemSettings;
  onUpdateSettings: (patch: Partial<SystemSettings>) => void;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ settings, onUpdateSettings }) => {
  const { t, lang } = useTranslation();
  const [stores, setStores] = useState<StoreConfig[]>([]);
  const [storeName, setStoreName] = useState('Основной магазин');
  const [consumerKey, setConsumerKey] = useState('');
  const [consumerSecret, setConsumerSecret] = useState('');
  const [bridgeToken, setBridgeToken] = useState('');
  const [suffixText, setSuffixText] = useState(settings.shortDescriptionSuffix || '');
  const [cmsFeedback, setCmsFeedback] = useState<string | null>(null);

  const [targetSlot, setTargetSlot] = useState<'visionProvider' | 'imageGenProvider' | 'llmCopywriter'>('visionProvider');
  const [rawSecret, setRawSecret] = useState('');
  const [secretFeedback, setSecretFeedback] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  const loadStores = async () => {
    try {
      const res = await apiClient.listStores();
      setStores(res.stores);
      if (res.stores.length > 0 && !settings.activeStoreId) {
        const first = res.stores[0];
        setStoreName(first.name);
        setSuffixText(first.settings?.short_description_suffix || '');
        onUpdateSettings({
          activeStoreId: first.id,
          cmsConnectorType: first.platform,
          cmsStoreUrl: first.base_url,
          shortDescriptionSuffix: first.settings?.short_description_suffix || '',
        });
      }
    } catch {
      /* локальный офлайн режим */
    }
  };

  useEffect(() => {
    void loadStores();
  }, []);

  const handleSelectStore = (idStr: string) => {
    if (idStr === 'new') {
      setStoreName('Новый магазин');
      setSuffixText('');
      onUpdateSettings({ activeStoreId: undefined, cmsStoreUrl: '' });
      return;
    }
    const found = stores.find((s) => s.id === Number(idStr));
    if (found) {
      setStoreName(found.name);
      setSuffixText(found.settings?.short_description_suffix || '');
      onUpdateSettings({
        activeStoreId: found.id,
        cmsConnectorType: found.platform,
        cmsStoreUrl: found.base_url,
        shortDescriptionSuffix: found.settings?.short_description_suffix || '',
      });
    }
  };

  const handleSaveStore = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settings.cmsStoreUrl.trim()) return;
    setIsSyncing(true);
    setCmsFeedback(null);
    const payload = {
      name: storeName.trim() || 'Магазин CMS',
      platform: settings.cmsConnectorType,
      base_url: settings.cmsStoreUrl.trim(),
      consumer_key: consumerKey || undefined,
      consumer_secret: consumerSecret || undefined,
      bridge_token: bridgeToken || undefined,
      settings: { short_description_suffix: suffixText },
    };
    try {
      const res = settings.activeStoreId
        ? await apiClient.updateStore(settings.activeStoreId, payload)
        : await apiClient.createStore(payload);
      setConsumerKey('');
      setConsumerSecret('');
      setBridgeToken('');
      onUpdateSettings({ activeStoreId: res.store.id, shortDescriptionSuffix: suffixText });
      await loadStores();
      setCmsFeedback(`Магазин #${res.store.id} сохранён, ключи зашифрованы в AES-256.`);
    } catch (err) {
      setCmsFeedback(`Ошибка сохранения: ${err instanceof Error ? err.message : 'Сбой сети'}`);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleCheckCms = async () => {
    if (!settings.activeStoreId) return;
    setIsSyncing(true);
    try {
      const res = await apiClient.checkStoreConnection(settings.activeStoreId);
      onUpdateSettings({ cmsConnectionStatus: res.connected ? 'connected' : 'error' });
      setCmsFeedback(res.connected ? `Связь с CMS подтверждена (${res.mode}).` : 'CMS не ответила.');
    } catch (err) {
      onUpdateSettings({ cmsConnectionStatus: 'error' });
      setCmsFeedback(`Ошибка проверки связи: ${err instanceof Error ? err.message : 'Сбой'}`);
    } finally {
      setIsSyncing(false);
    }
  };
  const handleSaveSecret = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rawSecret.trim()) return;
    setIsSyncing(true);
    try {
      const res = await apiClient.maskSecret(rawSecret.trim());
      onUpdateSettings({ maskedApiKeys: { ...settings.maskedApiKeys, [targetSlot]: res.masked_preview } });
      setRawSecret('');
      setSecretFeedback(`Ключ зашифрован (AES-256): ${res.masked_preview}`);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleRefreshBudget = async () => {
    setIsSyncing(true);
    try {
      const health = await apiClient.getHealth(lang);
      if (health.budget) {
        onUpdateSettings({ dailySpentUsd: health.budget.spent_today_usd, dailyBudgetLimitUsd: health.budget.daily_limit_usd });
      }
      setSecretFeedback(`Синхронизировано (${health.app_mode} / ${health.provider})`);
    } finally {
      setIsSyncing(false);
    }
  };

  const budgetPercent = Math.min(100, Math.round((settings.dailySpentUsd / Math.max(1, settings.dailyBudgetLimitUsd)) * 100));

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900">{t('settings.header')}</h2>
        <button onClick={handleRefreshBudget} disabled={isSyncing} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 cursor-pointer">
          <RefreshCw className="w-3.5 h-3.5 text-blue-600" />
          Проверить статус API
        </button>
      </div>

      <form onSubmit={handleSaveStore} className="bg-white p-6 rounded-xl border border-slate-200 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 font-semibold text-slate-900">
            <Server className="w-5 h-5 text-blue-600" />
            {t('settings.cms_section')}
          </div>
          {settings.activeStoreId && (
            <button type="button" onClick={handleCheckCms} disabled={isSyncing} className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg cursor-pointer">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Проверить связь с CMS
            </button>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Активный магазин (БД)</label>
            <select value={settings.activeStoreId ?? 'new'} onChange={(e) => handleSelectStore(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white">
              <option value="new">+ Добавить новый магазин</option>
              {stores.map((s) => (
                <option key={s.id} value={s.id}>#{s.id} — {s.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Название магазина</label>
            <input type="text" value={storeName} onChange={(e) => setStoreName(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg" />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Тип коннектора CMS</label>
            <select value={settings.cmsConnectorType} onChange={(e) => onUpdateSettings({ cmsConnectorType: e.target.value as SystemSettings['cmsConnectorType'] })} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white">
              <option value="woocommerce">WordPress / WooCommerce</option>
              <option value="shopify">Shopify Admin API</option>
              <option value="bitrix">1C-Bitrix REST</option>
              <option value="opencart">OpenCart API Bridge</option>
              <option value="custom_api">Universal JSON Webhook</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">URL магазина</label>
            <input type="text" value={settings.cmsStoreUrl} onChange={(e) => onUpdateSettings({ cmsStoreUrl: e.target.value })} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg" />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Суффикс краткого описания (шорткод CMS)</label>
            <input type="text" placeholder="[custom_form id='1']" value={suffixText} onChange={(e) => setSuffixText(e.target.value)} className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg font-mono" />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input type="password" placeholder="Consumer Key (ck_...)" value={consumerKey} onChange={(e) => setConsumerKey(e.target.value)} className="px-3 py-2 text-xs border border-slate-300 rounded-lg" />
          <input type="password" placeholder="Consumer Secret (cs_...)" value={consumerSecret} onChange={(e) => setConsumerSecret(e.target.value)} className="px-3 py-2 text-xs border border-slate-300 rounded-lg" />
          <input type="password" placeholder="WP Bridge Token (X-Bridge-Auth)" value={bridgeToken} onChange={(e) => setBridgeToken(e.target.value)} className="px-3 py-2 text-xs border border-slate-300 rounded-lg" />
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">Пустые поля ключей при обновлении не перезатирают сохранённые секреты.</span>
          <button type="submit" disabled={isSyncing} className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer">
            <Plus className="w-3.5 h-3.5" />
            Сохранить магазин в БД (AES-256)
          </button>
        </div>
        {cmsFeedback && <div className="text-xs text-blue-800 bg-blue-50 border border-blue-200 px-3 py-2 rounded-lg">{cmsFeedback}</div>}
      </form>

      <div className="bg-white p-6 rounded-xl border border-slate-200 space-y-4">
        <div className="flex items-center gap-2 font-semibold text-slate-900">
          <ShieldCheck className="w-5 h-5 text-emerald-600" />
          {t('settings.secrets_section')}
        </div>
        <form onSubmit={handleSaveSecret} className="grid grid-cols-1 md:grid-cols-12 gap-3">
          <select value={targetSlot} onChange={(e) => setTargetSlot(e.target.value as 'visionProvider' | 'imageGenProvider' | 'llmCopywriter')} className="md:col-span-4 px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white">
            <option value="visionProvider">Vision VLM Gateway</option>
            <option value="imageGenProvider">Image Generation Gateway</option>
            <option value="llmCopywriter">LLM Copywriter & SEO</option>
          </select>
          <input type="password" placeholder="Введите API-ключ ИИ" value={rawSecret} onChange={(e) => setRawSecret(e.target.value)} className="md:col-span-5 px-3 py-2 text-xs border border-slate-300 rounded-lg" />
          <button type="submit" disabled={isSyncing || !rawSecret.trim()} className="md:col-span-3 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold bg-slate-900 text-white rounded-lg cursor-pointer">
            <KeyRound className="w-3.5 h-3.5" />
            Сохранить в AES-256
          </button>
        </form>
        {secretFeedback && <div className="text-xs text-blue-800 bg-blue-50 border border-blue-200 px-3 py-2 rounded-lg">{secretFeedback}</div>}
      </div>

      <div className="bg-white p-6 rounded-xl border border-slate-200 space-y-4">
        <div className="flex items-center gap-2 font-semibold text-slate-900">
          <DollarSign className="w-5 h-5 text-amber-600" />
          {t('settings.budget_section')} (${settings.dailySpentUsd.toFixed(2)} / ${settings.dailyBudgetLimitUsd.toFixed(2)}, {budgetPercent}%)
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="flex items-center justify-between p-3 rounded-lg border border-slate-200 cursor-pointer">
            <span className="flex items-center gap-2 text-sm font-medium text-slate-800"><Cpu className="w-4 h-4 text-indigo-600" />{t('settings.vision_toggle')}</span>
            <input type="checkbox" checked={settings.enableDeepVision} onChange={(e) => onUpdateSettings({ enableDeepVision: e.target.checked })} className="w-4 h-4 accent-blue-600" />
          </label>
          <label className="flex items-center justify-between p-3 rounded-lg border border-slate-200 cursor-pointer">
            <span className="flex items-center gap-2 text-sm font-medium text-slate-800"><ShieldCheck className="w-4 h-4 text-indigo-600" />{t('settings.critic_toggle')}</span>
            <input type="checkbox" checked={settings.enableAutoCritic} onChange={(e) => onUpdateSettings({ enableAutoCritic: e.target.checked })} className="w-4 h-4 accent-blue-600" />
          </label>
        </div>
      </div>
    </div>
  );
};
