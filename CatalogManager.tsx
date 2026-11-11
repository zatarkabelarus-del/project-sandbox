import React, { useRef, useState } from 'react';
import {
  RefreshCw,
  FileSpreadsheet,
  Upload,
  CheckCircle2,
  AlertCircle,
  Clock,
  Play,
  Palette,
} from 'lucide-react';
import { ProductItem, TaskStatus } from '../../types/schema';
import { useTranslation } from '../../i18n/LanguageContext';

interface CatalogManagerProps {
  products: ProductItem[];
  onSelectForPilot: (product: ProductItem) => void;
  onRunBatch: () => void;
  onDirectUpload: (file: File) => void;
  onSyncCms: () => void;
  onImportCsv: () => void;
}

const STATUS_BADGE_STYLES: Record<TaskStatus, string> = {
  PENDING: 'bg-slate-100 text-slate-700 border-slate-300',
  DOWNLOADING: 'bg-sky-50 text-sky-700 border-sky-200',
  ANALYZING: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  GENERATING_BG: 'bg-purple-50 text-purple-700 border-purple-200',
  PILOT_REVIEW: 'bg-amber-50 text-amber-800 border-amber-300 font-semibold',
  BATCH_PROCESSING: 'bg-blue-50 text-blue-700 border-blue-200',
  READY_TO_PUBLISH: 'bg-teal-50 text-teal-700 border-teal-200',
  UPLOADING: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  SUCCESS: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  FAILED: 'bg-rose-50 text-rose-700 border-rose-300',
};

export const CatalogManager: React.FC<CatalogManagerProps> = ({
  products,
  onSelectForPilot,
  onRunBatch,
  onDirectUpload,
  onSyncCms,
  onImportCsv,
}) => {
  const { t } = useTranslation();
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const filteredProducts =
    statusFilter === 'ALL'
      ? products
      : products.filter((item) => item.status === statusFilter);

  const approvedCount = products.filter((p) => p.pilotApproved).length;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onDirectUpload(file);
      e.target.value = '';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">{t('catalog.header')}</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Всего позиций: {products.length} • Утверждено эталонов: {approvedCount}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={onSyncCms}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 transition cursor-pointer"
          >
            <RefreshCw className="w-4 h-4 text-blue-600" />
            {t('catalog.sync_cms')}
          </button>

          <button
            onClick={onImportCsv}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 transition cursor-pointer"
          >
            <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
            {t('catalog.import_csv')}
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition cursor-pointer"
          >
            <Upload className="w-4 h-4" />
            {t('catalog.direct_upload')}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="hidden"
          />

          <button
            onClick={onRunBatch}
            disabled={approvedCount === 0}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
          >
            <Play className="w-4 h-4" />
            {t('catalog.btn_run_batch')}
          </button>
        </div>
      </div>

      {/* Фильтр по статусам FSM */}
      <div className="flex flex-wrap items-center gap-2 bg-white p-3 rounded-xl border border-slate-200">
        {(['ALL', 'PILOT_REVIEW', 'BATCH_PROCESSING', 'READY_TO_PUBLISH', 'SUCCESS', 'FAILED'] as const).map(
          (st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer ${
                statusFilter === st
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {st === 'ALL' ? t('catalog.filter_all') : t(`status.${st}`)}
            </button>
          )
        )}
      </div>

      {/* Таблица товаров */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-xs uppercase text-slate-500">
                <th className="py-3.5 px-4">{t('catalog.col_sku')}</th>
                <th className="py-3.5 px-4">{t('catalog.col_product')}</th>
                <th className="py-3.5 px-4">{t('catalog.col_channel')}</th>
                <th className="py-3.5 px-4">{t('catalog.col_status')}</th>
                <th className="py-3.5 px-4 text-right">{t('catalog.col_actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-sm">
              {filteredProducts.map((product) => (
                <tr key={product.id} className="hover:bg-slate-50/80 transition">
                  <td className="py-3.5 px-4 font-mono text-xs text-slate-600 whitespace-nowrap">
                    {product.sku}
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-3">
                      <img
                        src={product.generatedPreviewUrl || product.originalImageUrl}
                        alt={product.name}
                        className="w-12 h-12 rounded-lg object-cover border border-slate-200 bg-slate-100 shrink-0"
                      />
                      <div>
                        <div className="font-medium text-slate-900">{product.name}</div>
                        <div className="text-xs text-slate-500">{product.category}</div>
                        {product.errorMessage && (
                          <div className="text-xs text-rose-600 mt-1 flex items-center gap-1">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                            {product.errorMessage}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-700">
                      {t(`channel.${product.channel}`)}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border ${
                        STATUS_BADGE_STYLES[product.status]
                      }`}
                    >
                      {product.status === 'SUCCESS' && <CheckCircle2 className="w-3.5 h-3.5" />}
                      {product.status === 'FAILED' && <AlertCircle className="w-3.5 h-3.5" />}
                      {product.status !== 'SUCCESS' && product.status !== 'FAILED' && (
                        <Clock className="w-3.5 h-3.5" />
                      )}
                      {t(`status.${product.status}`)}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-right whitespace-nowrap">
                    <button
                      onClick={() => onSelectForPilot(product)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 transition cursor-pointer"
                    >
                      <Palette className="w-3.5 h-3.5" />
                      {t('catalog.btn_open_pilot')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
