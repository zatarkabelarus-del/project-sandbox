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
  Download,
  Plus,
  X,
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
  const [zipFormat, setZipFormat] = useState<'webp' | 'jpeg' | 'avif' | 'png'>('webp');
  const [isExportingZip, setIsExportingZip] = useState(false);
  const [showManualModal, setShowManualModal] = useState(false);
  const [manualSku, setManualSku] = useState('');
  const [manualTitle, setManualTitle] = useState('');
  const [manualCategory, setManualCategory] = useState('');
  const [manualShortDesc, setManualShortDesc] = useState('');
  const [manualFullDesc, setManualFullDesc] = useState('');
  const [manualFile, setManualFile] = useState<File | null>(null);

  const handleManualSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualTitle.trim()) return;
    setIsBusy(true);
    setApiNotice(null);
    try {
      let imageDataUrl = '';
      if (manualFile) {
        imageDataUrl = await new Promise<string>((resolve) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ''));
          reader.readAsDataURL(manualFile);
        });
      }
      await apiClient.createManualProduct({
        sku: manualSku.trim() || `LOC-${Date.now().toString().slice(-5)}`,
        title: manualTitle.trim(),
        category: manualCategory.trim() || 'general',
        raw_short_description: manualShortDesc.trim(),
        raw_description: manualFullDesc.trim(),
        image_data_url: imageDataUrl,
      });
      if (manualFile) {
        onDirectUpload(manualFile);
      }
      setShowManualModal(false);
      setManualSku('');
      setManualTitle('');
      setManualCategory('');
      setManualShortDesc('');
      setManualFullDesc('');
      setManualFile(null);
      setApiNotice('Товар успешно добавлен в локальную очередь.');
    } catch (err) {
      setApiNotice(err instanceof Error ? err.message : 'Ошибка добавления товара');
    } finally {
      setIsBusy(false);
    }
  };

  const handleExportZip = async () => {
    setIsExportingZip(true);
    setApiNotice(null);
    try {
      const numericIds = products
        .map((p) => Number(p.id.replace(/\D/g, '')))
        .filter((n) => Number.isFinite(n) && n > 0);
      await apiClient.downloadZipPackage({
        product_ids: numericIds,
        output_format: zipFormat,
        output_quality: 90,
      });
      setApiNotice('ZIP-архив (слайды + catalog_ready.xlsx / .csv) успешно сформирован.');
    } catch (err) {
      setApiNotice(err instanceof Error ? err.message : 'Ошибка формирования ZIP-пакета');
    } finally {
      setIsExportingZip(false);
    }
  };

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
            onClick={() => setShowManualModal(true)}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 transition cursor-pointer"
          >
            <Plus className="w-4 h-4 text-indigo-600" />
            Карточка с ПК
          </button>

          <div className="inline-flex items-center rounded-lg border border-slate-300 bg-white overflow-hidden">
            <select
              value={zipFormat}
              onChange={(e) => setZipFormat(e.target.value as 'webp' | 'jpeg' | 'avif' | 'png')}
              className="px-2.5 py-2 text-xs font-semibold text-slate-700 bg-slate-50 border-r border-slate-200 outline-none"
              title="Формат слайдов в ZIP-архиве"
            >
              <option value="webp">WEBP</option>
              <option value="jpeg">JPEG</option>
              <option value="avif">AVIF</option>
              <option value="png">PNG</option>
            </select>
            <button
              onClick={handleExportZip}
              disabled={isExportingZip || products.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-40 transition cursor-pointer"
            >
              <Download className="w-4 h-4" />
              {isExportingZip ? 'Сборка ZIP...' : 'Скачать ZIP-пакет'}
            </button>
          </div>

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
            {showManualModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-900">Добавить товар с локальным фото</h3>
              <button
                onClick={() => setShowManualModal(false)}
                className="text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleManualSubmit} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Артикул (SKU)</label>
                  <input
                    type="text"
                    value={manualSku}
                    onChange={(e) => setManualSku(e.target.value)}
                    placeholder="ART-1001"
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">Категория</label>
                  <input
                    type="text"
                    value={manualCategory}
                    onChange={(e) => setManualCategory(e.target.value)}
                    placeholder="Каталог"
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Наименование товара *</label>
                <input
                  type="text"
                  required
                  value={manualTitle}
                  onChange={(e) => setManualTitle(e.target.value)}
                  placeholder="Введите название товара"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Фотография с ПК</label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setManualFile(e.target.files?.[0] || null)}
                  className="w-full text-xs text-slate-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-100 file:text-slate-700"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Краткое описание</label>
                <textarea
                  rows={2}
                  value={manualShortDesc}
                  onChange={(e) => setManualShortDesc(e.target.value)}
                  placeholder="Ключевые преимущества в 1–2 предложениях"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Полное описание</label>
                <textarea
                  rows={3}
                  value={manualFullDesc}
                  onChange={(e) => setManualFullDesc(e.target.value)}
                  placeholder="Подробные характеристики и комплектация"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowManualModal(false)}
                  className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg cursor-pointer"
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  disabled={isBusy || !manualTitle.trim()}
                  className="px-4 py-2 text-sm font-semibold bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 cursor-pointer"
                >
                  Сохранить товар
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
