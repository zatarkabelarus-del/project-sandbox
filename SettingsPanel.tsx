import React from 'react';
import { ShieldCheck, Server, DollarSign, Cpu } from 'lucide-react';
import { SystemSettings } from '../../types/schema';
import { useTranslation } from '../../i18n/LanguageContext';

interface SettingsPanelProps {
  settings: SystemSettings;
  onUpdateSettings: (patch: Partial<SystemSettings>) => void;
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ settings, onUpdateSettings }) => {
  const { t } = useTranslation();

  const budgetPercent = Math.min(
    100,
    Math.round((settings.dailySpentUsd / Math.max(1, settings.dailyBudgetLimitUsd)) * 100)
  );

  return (
    <div className="space-y-6 max-w-4xl">
      <h2 className="text-xl font-bold text-slate-900">{t('settings.header')}</h2>

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
