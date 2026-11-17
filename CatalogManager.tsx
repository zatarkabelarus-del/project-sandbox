import React, { useEffect, useRef, useState } from 'react';
import {
  RefreshCw,
  FileSpreadsheet,
  Upload,
  CheckCircle2,
  AlertCircle,
  Clock,
  Play,
  Palette,
  Square,
  Loader2,
} from 'lucide-react';
import { BatchJobStatus, ProductItem, TaskStatus } from '../../types/schema';
import { useTranslation } from '../../i18n/LanguageContext';
import { apiClient, TableImportReport } from '../../api/client';

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
  const { t, lang } = useTranslation();
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [importReport, setImportReport] = useState<TableImportReport | null>(null);
  const [apiNotice, setApiNotice] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [activeJob, setActiveJob] = useState<BatchJobStatus | null>(null);

  useEffect(() => {
    let isMounted = true;
    apiClient
      .getActiveBatchJob()
      .then((res) => {
        if (isMounted && res.job && (res.job.status === 'QUEUED' || res.job.status === 'RUNNING')) {
          setActiveJob(res.job);
        }
      })
      .catch(() => {
        // Offline / DEV_MOCK without backend
      });
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!activeJob || (activeJob.status !== 'QUEUED' && activeJob.status !== 'RUNNING')) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const updated = await apiClient.getBatchJobStatus(activeJob.job_id);
        setActiveJob(updated);
        if (updated.status === 'COMPLETED' || updated.status === 'CANCELLED' || updated.status === 'FAILED') {
          window.clearInterval(timer);
          onRunBatch();
        }
      } catch {
        window.clearInterval(timer);
      }
    }, 1500);

    return () => window.clearInterval(timer);
  }, [activeJob?.job_id, activeJob?.status]);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const tableInputRef = useRef<HTMLInputElement | null>(null);

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

  const handleTableFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setIsBusy(true);
    setApiNotice(null);
    try {
      const report = await apiClient.importCatalogTable(file);
      setImportReport(report);
      onImportCsv();
    } catch (err) {
      onImportCsv();
      setApiNotice(err instanceof Error ? err.message : 'Offline fallback import');
    } finally {
      setIsBusy(false);
    }
  };

  const handleBatchClick = async () => {
    setIsBusy(true);
    setApiNotice(null);
    try {
      const savedTplId = Number(localStorage.getItem('ai_pilot_template_id') || '1');
      const numericIds = products
        .map((p) => Number(p.id.replace(/\D/g, '')))
        .filter((n) => Number.isFinite(n) && n > 0);
      const targetIds = numericIds.length > 0 ? numericIds :[1];
      const res = await apiClient.runBatchSeries({
        pilot_template_id: savedTplId,
        product_ids: targetIds,
        lang,
        async_mode: true,
      });
      setActiveJob({
        job_id: res.job_id,
        pilot_template_id: res.pilot_template_id,
        status: 'QUEUED',
        total_items: res.total_items || targetIds.length,
        processed_items: 0,
        succeeded_count: 0,
        failed_count: 0,
        progress_percent: 0,
        current_sku: null,
        cancel_requested: false,
        error_summary: null,
      });
    } catch {
      onRunBatch();
    } finally {
      setIsBusy(false);
    }
  };

  const handleCancelBatch = async () => {
    if (!activeJob) return;
    try {
      const updated = await apiClient.cancelBatchJob(activeJob.job_id);
      setActiveJob(updated);
    } catch {
      // Ignore network error on cancel
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
            onClick={() => tableInputRef.current?.click()}
            disabled={isBusy}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 transition cursor-pointer"
          >
            <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
            {t('catalog.import_csv')}
          </button>
          <input
            ref={tableInputRef}
            type="file"
            accept=".csv,.xlsx"
            onChange={handleTableFileChange}
            className="hidden"
          />

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
            onClick={handleBatchClick}
            disabled={approvedCount === 0 || isBusy}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
          >
            <Play className="w-4 h-4" />
            {t('catalog.btn_run_batch')}
          </button>
        </div>
      </div>

      {activeJob && (
        <div className="bg-white border border-blue-200 rounded-xl p-4 shadow-xs space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              {(activeJob.status === 'QUEUED' || activeJob.status === 'RUNNING') && (
                <Loader2 className="w-4 h-4 text-blue-600 animate-spin shrink-0" />
              )}
              {activeJob.status === 'COMPLETED' && (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              )}
              {(activeJob.status === 'CANCELLED' || activeJob.status === 'FAILED') && (
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              )}
              <span className="text-sm font-semibold text-slate-900">
                Пакетная очередь ({activeJob.job_id}):{' '}
                {activeJob.processed_items} / {activeJob.total_items} ({activeJob.progress_percent}%)
              </span>
              {activeJob.current_sku && (
                <span className="text-xs font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                  SKU: {activeJob.current_sku}
                </span>
              )}
            </div>

            <div className="flex items-center gap-3 text-xs">
              <span className="text-emerald-700 font-medium">
                Успешно: {activeJob.succeeded_count}
              </span>
              {activeJob.failed_count > 0 && (
                <span className="text-rose-600 font-medium">
                  Ошибок: {activeJob.failed_count}
                </span>
              )}
              {(activeJob.status === 'QUEUED' || activeJob.status === 'RUNNING') ? (
                <button
                  onClick={handleCancelBatch}
                  disabled={activeJob.cancel_requested}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200 font-medium cursor-pointer disabled:opacity-50"
                >
                  <Square className="w-3 h-3" />
                  {activeJob.cancel_requested ? 'Остановка...' : 'Остановить'}
                </button>
              ) : (
                <button
                  onClick={() => setActiveJob(null)}
                  className="text-slate-500 hover:text-slate-800 cursor-pointer"
                >
                  Скрыть
                </button>
              )}
            </div>
          </div>

          <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                activeJob.status === 'COMPLETED'
                  ? 'bg-emerald-500'
                  : activeJob.status === 'CANCELLED'
                    ? 'bg-amber-500'
                    : 'bg-blue-600'
              }`}
              style={{ width: `${Math.min(100, Math.max(0, activeJob.progress_percent))}%` }}
            />
          </div>
        </div>
      )}

      {importReport && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-semibold text-slate-900">
              Отчёт импорта таблицы: всего строк {importReport.total_rows}, загружено{' '}
              <span className="text-emerald-600">{importReport.valid_count}</span>, ошибок{' '}
              <span className="text-rose-600">{importReport.error_count}</span>
            </span>
            <button
              onClick={() => setImportReport(null)}
              className="text-xs text-slate-500 hover:text-slate-800 cursor-pointer"
            >
              Скрыть
            </button>
          </div>
          {importReport.errors.length > 0 && (
            <div className="max-h-28 overflow-y-auto text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-2.5 space-y-1">
              {importReport.errors.map((err, i) => (
                <div key={i}>
                  Строка #{err.row}: {err.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {apiNotice && (
        <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 px-3.5 py-2 rounded-lg">
          {apiNotice}
        </div>
      )}

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
