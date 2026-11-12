import React, { useState } from 'react';
import { ShieldCheck, Server, DollarSign, Cpu, KeyRound, RefreshCw } from 'lucide-react';
import { SystemSettings } from '../../types/schema';
import { useTranslation } from '../../i18n/LanguageContext';
import { apiClient } from '../../api/client';

interface SettingsPanelProps {
  settings: SystemSettings;
  onUpdateSettings: (patch: Partial<SystemSettings>) => void;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ settings, onUpdateSettings }) => {
  const { t, lang } = useTranslation();
  const [targetSlot, setTargetSlot] = useState<'visionProvider' | 'imageGenProvider' | 'llmCopywriter'>('visionProvider');
  const [rawSecret, setRawSecret] = useState('');
  const [secretFeedback, setSecretFeedback] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  const budgetPercent = Math.min(
    100,
    Math.round((settings.dailySpentUsd / Math.max(1, settings.dailyBudgetLimitUsd)) * 100)
  );

  const handleSaveSecret = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rawSecret.trim()) return;
    setIsSyncing(true);
    setSecretFeedback(null);
    try {
      const res = await apiClient.maskSecret(rawSecret.trim());
      onUpdateSettings({
        maskedApiKeys: {
          ...settings.maskedApiKeys,
          [targetSlot]: res.masked_preview,
        },
      });
      setRawSecret('');
      setSecretFeedback(`Ключ зашифрован (AES-256) на сервере: ${res.masked_preview}`);
    } catch {
      const fallbackMask =
        rawSecret.length > 6 ? `${rawSecret.slice(0, 3)}****${rawSecret.slice(-3)}` : '****';
      onUpdateSettings({
        maskedApiKeys: {
          ...settings.maskedApiKeys,
          [targetSlot]: fallbackMask,
        },
      });
      setRawSecret('');
      setSecretFeedback(`Локальная маскировка (DEV_MOCK): ${fallbackMask}`);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleRefreshBudget = async () => {
    setIsSyncing(true);
    try {
      const health = await apiClient.getHealth(lang);
      if (health.budget) {
        onUpdateSettings({
          dailySpentUsd: health.budget.spent_today_usd,
          dailyBudgetLimitUsd: health.budget.daily_limit_usd,
        });
      }
      setSecretFeedback(`Синхронизировано с бэкендом (${health.app_mode} / ${health.provider})`);
    } catch {
      setSecretFeedback('Бэкенд недоступен, отображаются локальные лимиты.');
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900">{t('settings.header')}</h2>
        <button
          onClick={handleRefreshBudget}
          disabled={isSyncing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 cursor-pointer"
        >
          <RefreshCw className="w-3.5 h-3.5 text-blue-600" />
          Проверить статус API
        </button>
      </div>

      <div className="bg-white p-6 rounded-xl border border-slate-200 space-y-4">
        <div className="flex items-center gap-2 font-semibold text-slate-900">
          <Server className="w-5 h-5 text-blue-600" />
          {t('settings.cms_section')}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              Тип коннектора CMS
            </label>
            <select
              value={settings.cmsConnectorType}
              onChange={(e) =>
                onUpdateSettings({
                  cmsConnectorType: e.target.value as SystemSettings['cmsConnectorType'],
                })
              }
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white"
            >
              <option value="woocommerce">WordPress / WooCommerce (REST API)</option>
              <option value="shopify">Shopify Admin API</option>
              <option value="bitrix">1C-Bitrix REST</option>
              <option value="opencart">OpenCart API Bridge</option>
              <option value="custom_api">Universal JSON Webhook</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              URL магазина / шлюза
            </label>
            <input
              type="text"
              value={settings.cmsStoreUrl}
              onChange={(e) => onUpdateSettings({ cmsStoreUrl: e.target.value })}
              className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
            />
          </div>
        </div>
      </div>
      <div className="bg-white p-6 rounded-xl border border-slate-200 space-y-4">
        <div className="flex items-center gap-2 font-semibold text-slate-900">
          <ShieldCheck className="w-5 h-5 text-emerald-600" />
          {t('settings.secrets_section')}
        </div>

        <p className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 px-3 py-2 rounded-lg">
          {t('settings.secrets_notice')}
        </p>

        <form onSubmit={handleSaveSecret} className="grid grid-cols-1 md:grid-cols-12 gap-3">
          <select
            value={targetSlot}
            onChange={(e) =>
              setTargetSlot(
                e.target.value as 'visionProvider' | 'imageGenProvider' | 'llmCopywriter'
              )
            }
            className="md:col-span-4 px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white"
          >
            <option value="visionProvider">Vision VLM Gateway</option>
            <option value="imageGenProvider">Image Generation Gateway</option>
            <option value="llmCopywriter">LLM Copywriter & SEO</option>
          </select>

          <input
            type="password"
            placeholder="Введите API-ключ (передаётся только на бэкенд)"
            value={rawSecret}
            onChange={(e) => setRawSecret(e.target.value)}
            className="md:col-span-5 px-3 py-2 text-xs border border-slate-300 rounded-lg"
          />

          <button
            type="submit"
            disabled={isSyncing || !rawSecret.trim()}
            className="md:col-span-3 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-semibold bg-slate-900 text-white rounded-lg hover:bg-slate-800 disabled:opacity-40 cursor-pointer"
          >
            <KeyRound className="w-3.5 h-3.5" />
            Сохранить в AES-256
          </button>
        </form>

        {secretFeedback && (
          <div className="text-xs text-blue-800 bg-blue-50 border border-blue-200 px-3 py-2 rounded-lg">
            {secretFeedback}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <div className="text-slate-500 mb-1">Vision VLM Gateway</div>
            <div className="font-mono text-slate-800">{settings.maskedApiKeys.visionProvider}</div>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <div className="text-slate-500 mb-1">Image Generation Gateway</div>
            <div className="font-mono text-slate-800">
              {settings.maskedApiKeys.imageGenProvider}
            </div>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <div className="text-slate-500 mb-1">LLM Copywriter & SEO</div>
            <div className="font-mono text-slate-800">{settings.maskedApiKeys.llmCopywriter}</div>
          </div>
        </div>
      </div>

      <div className="bg-white p-6 rounded-xl border border-slate-200 space-y-5">
        <div className="flex items-center gap-2 font-semibold text-slate-900">
          <DollarSign className="w-5 h-5 text-amber-600" />
          {t('settings.budget_section')}
        </div>

        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-slate-600">
              Расход за сегодня: <strong>${settings.dailySpentUsd.toFixed(2)}</strong>
            </span>
            <span className="text-slate-600">
              Лимит: <strong>${settings.dailyBudgetLimitUsd.toFixed(2)}</strong> ({budgetPercent}%)
            </span>
          </div>
          <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-600 transition-all"
              style={{ width: `${budgetPercent}%` }}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-slate-200">
          <label className="flex items-center justify-between p-3 rounded-lg border border-slate-200 cursor-pointer">
            <span className="flex items-center gap-2 text-sm font-medium text-slate-800">
              <Cpu className="w-4 h-4 text-indigo-600" />
              {t('settings.vision_toggle')}
            </span>
            <input
              type="checkbox"
              checked={settings.enableDeepVision}
              onChange={(e) => onUpdateSettings({ enableDeepVision: e.target.checked })}
              className="w-4 h-4 accent-blue-600"
            />
          </label>

          <label className="flex items-center justify-between p-3 rounded-lg border border-slate-200 cursor-pointer">
            <span className="flex items-center gap-2 text-sm font-medium text-slate-800">
              <ShieldCheck className="w-4 h-4 text-indigo-600" />
              {t('settings.critic_toggle')}
            </span>
            <input
              type="checkbox"
              checked={settings.enableAutoCritic}
              onChange={(e) => onUpdateSettings({ enableAutoCritic: e.target.checked })}
              className="w-4 h-4 accent-blue-600"
            />
          </label>
        </div>
      </div>
    </div>
  );
};
