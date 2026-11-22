import React, { useEffect, useRef, useState } from 'react';
import { Stage, Layer, Rect, Text, Group, Image as KonvaImage } from 'react-konva';
import Konva from 'konva';
import { CheckCircle, Download, Plus, Trash2, Layers, Sparkles, Send, Image as ImageIcon, Scissors, Upload } from 'lucide-react';
import { AIImageModelItem, BrandLogoConfig, CanvasAspectPreset, CanvasLayerItem, ImageOutputFormat, LayoutSchema, ProductItem, SavedPlateStyleItem, UserAssetItem } from '../../types/schema';
import { useTranslation } from '../../i18n/LanguageContext';
import { apiClient } from '../../api/client';

interface PilotEditorProps {
  product: ProductItem;
  defaultFormat?: ImageOutputFormat;
  defaultQuality?: number;
  onApprovePilot: (productId: string, updatedProduct: ProductItem) => void;
}

const FORMAT_MIME_MAP: Record<ImageOutputFormat, { mime: string; ext: string }> = {
  webp: { mime: 'image/webp', ext: 'webp' },
  jpeg: { mime: 'image/jpeg', ext: 'jpg' },
  avif: { mime: 'image/avif', ext: 'avif' },
  png: { mime: 'image/png', ext: 'png' },
};

const CANVAS_PRESETS: Record<Exclude<CanvasAspectPreset, 'custom'>, { label: string; w: number; h: number }> = {
  '1:1': { label: '1:1 (1080×1080)', w: 1080, h: 1080 },
  '3:4': { label: '3:4 (1080×1440)', w: 1080, h: 1440 },
  '9:16': { label: '9:16 (1080×1920)', w: 1080, h: 1920 },
  '16:9': { label: '16:9 (1920×1080)', w: 1920, h: 1080 },
};

const FONT_FAMILIES = ['Inter', 'Montserrat', 'Roboto', 'Oswald', 'Playfair Display'];

const useLoadedImage = (url: string) => {
  const[image, setImage] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!url) return;
    const img = new window.Image();
    img.crossOrigin = 'anonymous';
    img.src = url;
    img.onload = () => setImage(img);
  }, [url]);
  return image;
};

export const PilotEditor: React.FC<PilotEditorProps> = ({
  product,
  defaultFormat = 'webp',
  defaultQuality = 90,
  onApprovePilot,
}) => {
  const { t, lang } = useTranslation();
  const stageRef = useRef<Konva.Stage | null>(null);

  const initialSlides =
    product.slides.length > 0
      ? product.slides
      : [
          {
            slideIndex: 1,
            slideRole: 'Главный оффер',
            backgroundUrl: product.generatedPreviewUrl || product.originalImageUrl,
            productCutoutUrl: '',
            productBBox: { x: 250, y: 240, width: 300, height: 340 },
            layers: [
              {
                id: 'default-badge',
                type: 'badge' as const,
                text: 'ХИТ ПРОДАЖ',
                x: 40,
                y: 40,
                width: 220,
                height: 46,
                bgColor: '#2563eb',
                textColor: '#ffffff',
                fontSize: 18,
                borderRadius: 10,
              },
            ],
          },
        ];

  const [slides, setSlides] = useState(initialSlides);
  const [activeSlideIdx, setActiveSlideIdx] = useState(0);
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(
    initialSlides.at(0)?.layers.at(0)?.id || null
  );
  const [exportFormat, setExportFormat] = useState<ImageOutputFormat>(defaultFormat);
  const [exportQuality, setExportQuality] = useState<number>(defaultQuality);
  const [backendTaskId, setBackendTaskId] = useState<number | null>(null);
  const [backendProductId, setBackendProductId] = useState<number>(1);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lockBackgrounds, setLockBackgrounds] = useState(true);
  const [lockPlateStyle, setLockPlateStyle] = useState(true);
  const [myBackgrounds, setMyBackgrounds] = useState<UserAssetItem[]>([]);
  const [modelsCatalog, setModelsCatalog] = useState<AIImageModelItem[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('nanobanana-flash');
  const [slidesCount, setSlidesCount] = useState<number>(
    Math.min(8, Math.max(1, initialSlides.length || 5))
  );
  const [avoidTitleDuplication, setAvoidTitleDuplication] = useState<boolean>(false);
  const [myPlates, setMyPlates] = useState<SavedPlateStyleItem[]>([]);
  const [libraryTab, setLibraryTab] = useState<'none' | 'backgrounds' | 'plates'>('none');
  const [aspectPreset, setAspectPreset] = useState<CanvasAspectPreset>('1:1');
  const [canvasW, setCanvasW] = useState<number>(1080);
  const [canvasH, setCanvasH] = useState<number>(1080);
  const [brandLogo, setBrandLogo] = useState<BrandLogoConfig>({
    url: '',
    position: 'top-right',
    sizePx: 110,
    opacity: 0.92,
  });
  const bgFileInputRef = useRef<HTMLInputElement | null>(null);
  const logoFileInputRef = useRef<HTMLInputElement | null>(null);

  const refreshSavedLibraries = async () => {
    try {
      const [bgRes, plRes] = await Promise.all([
        apiClient.getMyBackgrounds(),
        apiClient.getMyPlates(),
      ]);
      setMyBackgrounds(bgRes.items || []);
      setMyPlates(plRes.items || []);
    } catch {
      // Игнорируем в офлайн-режиме
    }
  };

  useEffect(() => {
    refreshSavedLibraries();
    apiClient
      .getModelsCatalog()
      .then((res) => {
        if (Array.isArray(res.models) && res.models.length > 0) {
          setModelsCatalog(res.models);
          setSelectedModel(res.default_model || res.models.at(0)!.id);
        }
      })
      .catch(() => {
        // Офлайн-фоллбэк
      });
  }, []);

  useEffect(() => {
    setExportFormat(defaultFormat);
  }, [defaultFormat]);

  useEffect(() => {
    setExportQuality(defaultQuality);
  }, [defaultQuality]);

  useEffect(() => {
    setSlides(initialSlides);
    setActiveSlideIdx(0);
    setSelectedLayerId(initialSlides.at(0)?.layers.at(0)?.id || null);
    setStatusBanner(null);
  }, [product.id]);
  const currentSlide = slides.at(activeSlideIdx) || slides.at(0)!;
  const bgImage = useLoadedImage(currentSlide.backgroundUrl);
    const cutoutImage = useLoadedImage(currentSlide.productCutoutUrl || '');
  const logoImage = useLoadedImage(brandLogo.url);
  const selectedLayer = currentSlide.layers.find((l) => l.id === selectedLayerId) || null;

  const updateLayer = (layerId: string, patch: Partial<CanvasLayerItem>) => {
    setSlides((prev) =>
      prev.map((slide, idx) => {
        if (idx !== activeSlideIdx) return slide;
        return {
          ...slide,
          layers: slide.layers.map((layer) =>
            layer.id === layerId ? { ...layer, ...patch } : layer
          ),
        };
      })
    );
  };

  const handleAddLayer = () => {
    const newLayer: CanvasLayerItem = {
      id: `layer-${Date.now()}`,
      type: 'feature_box',
      text: 'Новое преимущество товара',
      x: 60,
      y: 560,
      width: 340,
      height: 52,
      bgColor: '#0f172a',
      textColor: '#ffffff',
      fontSize: 18,
      borderRadius: 10,
    };

    setSlides((prev) =>
      prev.map((slide, idx) =>
        idx === activeSlideIdx ? { ...slide, layers: [...slide.layers, newLayer] } : slide
      )
    );
    setSelectedLayerId(newLayer.id);
  };

  const handleDeleteLayer = (layerId: string) => {
    setSlides((prev) =>
      prev.map((slide, idx) =>
        idx === activeSlideIdx
          ? { ...slide, layers: slide.layers.filter((l) => l.id !== layerId) }
          : slide
      )
    );
    if (selectedLayerId === layerId) {
      setSelectedLayerId(null);
    }
  };

  const handleExportSlide = () => {
    if (!stageRef.current) return;
    const spec = FORMAT_MIME_MAP[exportFormat] || FORMAT_MIME_MAP.webp;
    const q = Math.max(0.4, Math.min(1, exportQuality / 100));
    let dataUrl = stageRef.current.toDataURL({ mimeType: spec.mime, quality: q });
    let finalExt = spec.ext;
    if (exportFormat === 'avif' && !dataUrl.startsWith('data:image/avif')) {
      dataUrl = stageRef.current.toDataURL({ mimeType: 'image/webp', quality: q });
      finalExt = 'webp';
    }
    const link = document.createElement('a');
    link.download = `${product.sku}-slide-${currentSlide.slideIndex}.${finalExt}`;
    link.href = dataUrl;
    link.click();
  };

  const handleGeneratePilotAI = async () => {
    setIsLoading(true);
    setStatusBanner(null);
    try {
      const res = await apiClient.runPilotPreview({
        product_id: product.sku,
        title: product.name,
        image_url: product.originalImageUrl,
        category: product.category,
        slides_count: slidesCount,
        image_model: selectedModel,
        avoid_title_duplication: avoidTitleDuplication,
        lang,
      });
      if (typeof res.task_id === 'number') setBackendTaskId(res.task_id);
      if (typeof res.db_product_id === 'number') setBackendProductId(res.db_product_id);

      if (Array.isArray(res.slides) && res.slides.length > 0) {
        const mappedSlides: LayoutSchema[] = res.slides.map((rawSlide: Record<string, unknown>, idx: number) => {
          const layoutObj = (rawSlide.layout_schema as Record<string, unknown>) || {};
          const rawLayers = Array.isArray(layoutObj.layers) ? (layoutObj.layers as Array<Record<string, unknown>>) : [];
          return {
            slideIndex: Number(rawSlide.slide_index || idx + 1),
            slideRole: String(rawSlide.role || `Слайд ${idx + 1}`),
            backgroundUrl: String(layoutObj.background_layer_url || product.generatedPreviewUrl || product.originalImageUrl),
            productCutoutUrl: currentSlide?.productCutoutUrl || '',
            productBBox: { x: 250, y: 240, width: 300, height: 340 },
            layers:
              rawLayers.length > 0
                ? rawLayers.map((lr, lIdx) => ({
                    id: String(lr.id || `ai-layer-${idx + 1}-${lIdx + 1}`),
                    type: (lr.type as CanvasLayerItem['type']) || 'feature_box',
                    text: String(lr.text || ''),
                    x: Math.round(Number(lr.x ?? 0.06) * canvasW),
                    y: Math.round(Number(lr.y ?? 0.08 + lIdx * 0.14) * canvasH),
                    width: Math.round(Number(lr.w ?? lr.width ?? 0.44) * canvasW),
                    height: Math.round(Number(lr.h ?? lr.height ?? 0.09) * canvasH),
                    bgColor: String(lr.bgColor || '#0f172a'),
                    textColor: String(lr.textColor || '#ffffff'),
                    fontSize: Number(lr.fontSize || 24),
                    borderRadius: Number(lr.borderRadius || 12),
                  }))
                : [
                    {
                      id: `ai-badge-${idx + 1}`,
                      type: 'badge',
                      text: String(rawSlide.role || `Слайд ${idx + 1}`),
                      x: 40,
                      y: 40,
                      width: 280,
                      height: 48,
                      bgColor: '#2563eb',
                      textColor: '#ffffff',
                      fontSize: 18,
                      borderRadius: 10,
                    },
                  ],
          };
        });
        setSlides(mappedSlides);
        setActiveSlideIdx(0);
        setSelectedLayerId(mappedSlides.at(0)?.layers.at(0)?.id || null);
      }

      setStatusBanner(
        `FSM: ${String(res.fsm_status_label || res.fsm_status || 'PILOT_REVIEW')} · Модель: ${selectedModel} · Слайдов: ${slidesCount}`
      );
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : 'Локальный режим Пилота');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePreviewCmsPublish = async () => {
    if (!backendTaskId) {
      setStatusBanner('Сначала нажмите «Сгенерировать ИИ-Пилот» для создания задачи в БД.');
      return;
    }
    setIsLoading(true);
    try {
      const res = await apiClient.publishToWooCommerce({
        task_id: backendTaskId,
        output_format: exportFormat,
        output_quality: exportQuality,
        preview_only: true,
        lang,
      });
      const mediaCount = Array.isArray(res.media_plan) ? res.media_plan.length : 0;
      setStatusBanner(
        `Предпросмотр CMS готов: ${mediaCount} SEO-медиафайлов (${exportFormat.toUpperCase()}, ${exportQuality}%) и HTML-блок.`
      );
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : 'Ошибка предпросмотра CMS');
    } finally {
      setIsLoading(false);
    }
  };

    const handleSelectAspect = (preset: CanvasAspectPreset) => {
    setAspectPreset(preset);
    if (preset !== 'custom') {
      setCanvasW(CANVAS_PRESETS[preset].w);
      setCanvasH(CANVAS_PRESETS[preset].h);
    }
  };

  const handleRemoveBgCpu = async () => {
    setIsLoading(true);
    try {
      const srcUrl = currentSlide.backgroundUrl || product.originalImageUrl;
      const res = await apiClient.removeProductBackground(srcUrl);
      setSlides((prev) =>
        prev.map((s, idx) => (idx === activeSlideIdx ? { ...s, productCutoutUrl: res.cutout_data_url } : s))
      );
      setStatusBanner(`Фон товара удалён локально (${res.engine}, расход токенов: 0).`);
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : 'Ошибка удаления фона');
    } finally {
      setIsLoading(false);
    }
  };

  const handleUploadBgFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.item(0);
    if (!file) return;
    try {
      const uploaded = await apiClient.uploadCustomBackground(file);
      setMyBackgrounds((prev) => [uploaded, ...prev]);
      setSlides((prev) =>
        prev.map((s, idx) => (idx === activeSlideIdx ? { ...s, backgroundUrl: uploaded.asset_url } : s))
      );
      setStatusBanner(`Свой фон «${uploaded.name}» загружен и применён.`);
    } catch {
      const reader = new FileReader();
      reader.onload = () => {
        const url = String(reader.result || '');
        setSlides((prev) => prev.map((s, idx) => (idx === activeSlideIdx ? { ...s, backgroundUrl: url } : s)));
      };
      reader.readAsDataURL(file);
    }
  };

  const handleUploadLogoFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.item(0);
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setBrandLogo((prev) => ({ ...prev, url: String(reader.result || '') }));
    reader.readAsDataURL(file);
  };

  const handleApprove = async () => {
    const spec = FORMAT_MIME_MAP[exportFormat] || FORMAT_MIME_MAP.webp;
    const bakedPreview = stageRef.current
      ? stageRef.current.toDataURL({ mimeType: spec.mime, quality: exportQuality / 100 })
      : product.generatedPreviewUrl;

    try {
      const approved = await apiClient.approvePilotTemplate({
        name: `Pilot-${product.sku}`,
        pilot_product_id: backendProductId,
        style_code: 'minimal_light',
        approved_layout_schema: {
          lock_backgrounds: lockBackgrounds,
          lock_plate_style: lockPlateStyle,
          image_model: selectedModel,
          slides_count: slidesCount,
          avoid_title_duplication: avoidTitleDuplication,
          exportFormat,
          exportQuality,
          canvas_base: { width: canvasW, height: canvasH },
          brand_logo: brandLogo.url ? brandLogo : null,
          slides,
        },
      });
      localStorage.setItem('ai_pilot_template_id', String(approved.pilot_template_id));
      await refreshSavedLibraries();
      setStatusBanner(
        `Эталон #${approved.pilot_template_id} утверждён (${exportFormat.toUpperCase()}). Фоны и плашки сохранены в библиотеку.`
      );
    } catch {
      // Offline fallback in DEV_MOCK
    }

    onApprovePilot(product.id, {
      ...product,
      pilotApproved: true,
      status: 'READY_TO_PUBLISH',
      generatedPreviewUrl: bakedPreview,
      slides,
    });
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-slate-200">
        <div>
          <h2 className="text-lg font-bold text-slate-900">{t('pilot.header')}</h2>
          <p className="text-xs text-slate-500">
            {product.sku} — {product.name}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 bg-slate-50 px-2.5 py-1.5 rounded-lg border border-slate-200">
            <select
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value as ImageOutputFormat)}
              className="text-xs font-semibold text-slate-700 bg-transparent focus:outline-none cursor-pointer"
              title="Формат экспорта изображения"
            >
              <option value="webp">WebP</option>
              <option value="jpeg">JPEG (Pro)</option>
              <option value="avif">AVIF</option>
              <option value="png">PNG</option>
            </select>
            <span className="text-slate-300">|</span>
            <input
              type="number"
              min={40}
              max={100}
              value={exportQuality}
              disabled={exportFormat === 'png'}
              onChange={(e) => setExportQuality(Math.max(40, Math.min(100, Number(e.target.value) || 90)))}
              className="w-11 text-xs font-mono text-slate-700 bg-transparent text-right focus:outline-none"
              title="Качество сжатия (%)"
            />
            <span className="text-xs text-slate-400">%</span>
          </div>

          <button
            onClick={handleGeneratePilotAI}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-100 cursor-pointer"
          >
            <Sparkles className="w-4 h-4" />
            Сгенерировать ИИ-Пилот
          </button>

          <button
            onClick={handleRemoveBgCpu}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg hover:bg-emerald-100 cursor-pointer"
          >
            <Scissors className="w-4 h-4" />
            Вырезать фон (CPU)
          </button>

          <button
            onClick={handleExportSlide}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 cursor-pointer"
          >
            <Download className="w-4 h-4" />
            Скачать {exportFormat.toUpperCase()}
          </button>

          <button
            onClick={handlePreviewCmsPublish}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 cursor-pointer"
          >
            <Send className="w-4 h-4 text-teal-600" />
            Предпросмотр CMS
          </button>

          <button
            onClick={handleApprove}
            className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg text-white transition cursor-pointer ${
              product.pilotApproved
                ? 'bg-emerald-600 hover:bg-emerald-700'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            <CheckCircle className="w-4 h-4" />
            {product.pilotApproved ? t('pilot.approved_badge') : t('pilot.approve_btn')}
          </button>
        </div>
      </div>

      {statusBanner && (
        <div className="text-xs font-medium text-indigo-900 bg-indigo-50 border border-indigo-200 px-4 py-2.5 rounded-lg">
          {statusBanner}
        </div>
      )}

      <div className="bg-white px-4 py-3.5 rounded-xl border border-slate-200 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-slate-700">Модель ИИ:</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="px-2.5 py-1.5 text-xs font-semibold text-slate-800 bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-500 cursor-pointer"
            >
              {modelsCatalog.length > 0 ? (
                modelsCatalog.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} (×{m.cost_multiplier} ток.)
                  </option>
                ))
              ) : (
                <>
                  <option value="nanobanana-flash">NanoBanana (Gemini 2.5 Flash Image) (×1.0 ток.)</option>
                  <option value="nanobanana-pro">NanoBanana Pro (×2.0 ток.)</option>
                  <option value="flux-1-pro">Flux.1 Pro (×1.8 ток.)</option>
                </>
              )}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-slate-700">Слайдов в воронке:</label>
            <select
              value={slidesCount}
              onChange={(e) => setSlidesCount(Math.min(8, Math.max(1, Number(e.target.value) || 5)))}
              className="px-2.5 py-1.5 text-xs font-bold text-slate-800 bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:border-blue-500 cursor-pointer"
            >
              {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
                <option key={n} value={n}>
                  {n} {n === 1 ? 'слайд' : n < 5 ? 'слайда' : 'слайдов'}
                </option>
              ))}
            </select>
          </div>

          <label className="inline-flex items-center gap-2 text-xs font-semibold text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={avoidTitleDuplication}
              onChange={(e) => setAvoidTitleDuplication(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            Не дублировать название товара на слайдах
          </label>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-50 px-4 py-3 rounded-xl border border-slate-200">
        <div className="flex flex-wrap items-center gap-5">
          <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={lockBackgrounds}
              onChange={(e) => setLockBackgrounds(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            Фиксировать фоны по слайдам для всей серии
          </label>
          <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={lockPlateStyle}
              onChange={(e) => setLockPlateStyle(e.target.checked)}
              className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            Фиксировать стиль плашек (с автоподгонкой под длину текста)
          </label>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setLibraryTab(libraryTab === 'backgrounds' ? 'none' : 'backgrounds')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border cursor-pointer ${
              libraryTab === 'backgrounds'
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
            }`}
          >
            <ImageIcon className="w-3.5 h-3.5" />
            Мои фоны ({myBackgrounds.length})
          </button>
          <button
            type="button"
            onClick={() => setLibraryTab(libraryTab === 'plates' ? 'none' : 'plates')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border cursor-pointer ${
              libraryTab === 'plates'
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-100'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Мои плашки ({myPlates.length})
          </button>
        </div>
      </div>

      {libraryTab === 'backgrounds' && (
        <div className="bg-white p-4 rounded-xl border border-slate-200 space-y-2">
          <div className="text-xs font-bold text-slate-700">Сохранённые фоны из утверждённых пилотов (клик — применить к текущему слайду):</div>
                    <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-bold text-slate-700">Сохранённые фоны (клик — применить):</span>
            <div>
              <input ref={bgFileInputRef} type="file" accept="image/*" onChange={handleUploadBgFile} className="hidden" />
              <button
                type="button"
                onClick={() => bgFileInputRef.current?.click()}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer"
              >
                <Upload className="w-3.5 h-3.5" />
                Загрузить свой фон с ПК
              </button>
            </div>
          </div>

          {myBackgrounds.length === 0 ? (
            <div className="text-xs text-slate-400">Пока нет сохранённых фонов. Утвердите первый пилот, чтобы пополнить коллекцию.</div>
          ) : (
            <div className="flex flex-wrap gap-3">
              {myBackgrounds.map((bg) => (
                <button
                  key={bg.id}
                  type="button"
                  onClick={() =>
                    setSlides((prev) =>
                      prev.map((s, idx) => (idx === activeSlideIdx ? { ...s, backgroundUrl: bg.asset_url } : s))
                    )
                  }
                  className="group flex flex-col items-start border border-slate-200 rounded-lg p-1.5 hover:border-blue-500 cursor-pointer"
                >
                  <img src={bg.asset_url} alt={bg.name} className="w-20 h-20 object-cover rounded bg-slate-100" />
                  <span className="text-[11px] text-slate-600 mt-1 max-w-[80px] truncate">{bg.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {libraryTab === 'plates' && (
        <div className="bg-white p-4 rounded-xl border border-slate-200 space-y-2">
          <div className="text-xs font-bold text-slate-700">Сохранённые стили плашек (клик — применить ко всем плашкам текущего слайда):</div>
          {myPlates.length === 0 ? (
            <div className="text-xs text-slate-400">Пока нет сохранённых плашек. Утвердите первый пилот, чтобы сохранить его стиль.</div>
          ) : (
            <div className="flex flex-wrap gap-2.5">
              {myPlates.map((pl) => {
                const bgColor = pl.style_passport?.bgColor || '#0f172a';
                const textColor = pl.style_passport?.textColor || '#ffffff';
                const borderRadius = Number(pl.style_passport?.borderRadius ?? 10);
                return (
                  <button
                    key={pl.id}
                    type="button"
                    onClick={() =>
                      setSlides((prev) =>
                        prev.map((s, idx) =>
                          idx === activeSlideIdx
                            ? {
                                ...s,
                                layers: s.layers.map((l) => ({
                                  ...l,
                                  bgColor,
                                  textColor,
                                  borderRadius,
                                })),
                              }
                            : s
                        )
                      )
                    }
                    style={{ backgroundColor: bgColor, color: textColor, borderRadius: `${borderRadius}px` }}
                    className="px-3.5 py-2 text-xs font-bold shadow-sm hover:opacity-90 cursor-pointer"
                  >
                    {pl.name}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-slate-500 uppercase mr-2">
          {t('pilot.slide_selector')}:
        </span>
        {slides.map((s, idx) => (
          <button
            key={s.slideIndex}
            onClick={() => setActiveSlideIdx(idx)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition cursor-pointer ${
              idx === activeSlideIdx
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
            }`}
          >
            #{s.slideIndex} — {s.slideRole}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-7 bg-slate-200/70 p-4 rounded-xl border border-slate-300 flex justify-center items-center overflow-auto">
          <div className="bg-white shadow-md rounded-lg overflow-hidden border border-slate-300">
            {(() => {
              const previewScale = Math.min(540 / canvasW, 540 / canvasH);
              const logoPad = 28;
              const logoX = brandLogo.position.endsWith('right') ? canvasW - brandLogo.sizePx - logoPad : logoPad;
              const logoY = brandLogo.position.startsWith('bottom') ? canvasH - brandLogo.sizePx - logoPad : logoPad;
              return (
                <Stage
                  ref={stageRef}
                  width={Math.round(canvasW * previewScale)}
                  height={Math.round(canvasH * previewScale)}
                  scaleX={previewScale}
                  scaleY={previewScale}
                >
                  <Layer>
                    <Rect x={0} y={0} width={canvasW} height={canvasH} fill="#f8fafc" />
                    {bgImage && <KonvaImage image={bgImage} x={0} y={0} width={canvasW} height={canvasH} />}
                    {cutoutImage && (
                      <KonvaImage
                        image={cutoutImage}
                        x={Math.round(canvasW * 0.2)}
                        y={Math.round(canvasH * 0.2)}
                        width={Math.round(canvasW * 0.6)}
                        height={Math.round(canvasH * 0.6)}
                        draggable
                      />
                    )}
                    {logoImage && (
                      <KonvaImage
                        image={logoImage}
                        x={logoX}
                        y={logoY}
                        width={brandLogo.sizePx}
                        height={brandLogo.sizePx}
                        opacity={brandLogo.opacity}
                        draggable
                      />
                    )}
                  </Layer>

                  <Layer>
                    {currentSlide.layers.map((layer) => {
                      const isSelected = layer.id === selectedLayerId;
                      return (
                        <Group
                          key={layer.id}
                          x={layer.x}
                          y={layer.y}
                          draggable
                          onClick={() => setSelectedLayerId(layer.id)}
                          onTap={() => setSelectedLayerId(layer.id)}
                          onDragEnd={(e) =>
                            updateLayer(layer.id, { x: Math.round(e.target.x()), y: Math.round(e.target.y()) })
                          }
                        >
                          <Rect
                            width={layer.width}
                            height={layer.height}
                            fill={layer.bgColor}
                            cornerRadius={layer.borderRadius}
                            stroke={isSelected ? '#f59e0b' : undefined}
                            strokeWidth={isSelected ? 4 : 0}
                          />
                          <Text
                            text={layer.text}
                            width={layer.width}
                            height={layer.height}
                            fill={layer.textColor}
                            fontFamily={layer.fontFamily || 'Inter'}
                            fontSize={layer.fontSize}
                            fontStyle={layer.fontStyle || 'bold'}
                            lineHeight={layer.lineHeight || 1.2}
                            align="center"
                            verticalAlign="middle"
                            padding={10}
                          />
                        </Group>
                      );
                    })}
                  </Layer>
                </Stage>
              );
            })()}

          </div>
        </div>

        <div className="xl:col-span-5 bg-white p-5 rounded-xl border border-slate-200 space-y-5">
          <div className="flex items-center justify-between border-b border-slate-200 pb-3">
            <div className="flex items-center gap-2 font-semibold text-slate-900">
              <Layers className="w-4 h-4 text-blue-600" />
              {t('pilot.layers_title')}
            </div>
            <button
              onClick={handleAddLayer}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold bg-blue-50 text-blue-700 rounded-lg hover:bg-blue-100 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              {t('pilot.add_layer')}
            </button>
          </div>
          <div className="space-y-2 max-h-44 overflow-y-auto">
            {currentSlide.layers.map((layer) => (
              <div
                key={layer.id}
                onClick={() => setSelectedLayerId(layer.id)}
                className={`flex items-center justify-between p-2.5 rounded-lg border text-sm cursor-pointer ${
                  layer.id === selectedLayerId
                    ? 'border-blue-500 bg-blue-50/50'
                    : 'border-slate-200 hover:bg-slate-50'
                }`}
              >
                <span className="truncate font-medium text-slate-800">{layer.text}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteLayer(layer.id);
                  }}
                  className="text-slate-400 hover:text-rose-600 p-1 cursor-pointer"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          {selectedLayer && (
            <div className="space-y-4 pt-3 border-t border-slate-200">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  {t('pilot.text_label')}
                </label>
                <input
                  type="text"
                  value={selectedLayer.text}
                  onChange={(e) => updateLayer(selectedLayer.id, { text: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  Назначение слоя при серии
                </label>
                <select
                  value={selectedLayer.type}
                  onChange={(e) =>
                    updateLayer(selectedLayer.id, {
                      type: e.target.value as CanvasLayerItem['type'],
                    })
                  }
                  className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-lg bg-white"
                >
                  <option value="title">Заголовок товара (подставляется из товара)</option>
                  <option value="subtitle">Подзаголовок товара (подставляется из товара)</option>
                  <option value="feature_box">Преимущество товара (подставляется из товара)</option>
                  <option value="badge">Общий бейдж серии (сохраняет текст пилота)</option>
                </select>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">
                    {t('pilot.bg_color')}
                  </label>
                  <input
                    type="color"
                    value={selectedLayer.bgColor}
                    onChange={(e) => updateLayer(selectedLayer.id, { bgColor: e.target.value })}
                    className="w-full h-9 rounded border border-slate-300 cursor-pointer"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">
                    {t('pilot.text_color')}
                  </label>
                  <input
                    type="color"
                    value={selectedLayer.textColor}
                    onChange={(e) => updateLayer(selectedLayer.id, { textColor: e.target.value })}
                    className="w-full h-9 rounded border border-slate-300 cursor-pointer"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">
                    {t('pilot.font_size')}
                  </label>
                  <input
                    type="number"
                    min={12}
                    max={48}
                    value={selectedLayer.fontSize}
                    onChange={(e) =>
                      updateLayer(selectedLayer.id, { fontSize: Number(e.target.value) || 16 })
                    }
                    className="w-full px-2.5 py-1.5 text-sm border border-slate-300 rounded-lg"
                  />
                </div>
              </div>
                            <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs font-semibold text-slate-600 mb-1">Гарнитура шрифта</label>
                  <select
                    value={selectedLayer.fontFamily || 'Inter'}
                    onChange={(e) => updateLayer(selectedLayer.id, { fontFamily: e.target.value })}
                    className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white"
                  >
                    {FONT_FAMILIES.map((ff) => (
                      <option key={ff} value={ff}>{ff}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-600 mb-1">Начертание</label>
                  <select
                    value={selectedLayer.fontStyle || 'bold'}
                    onChange={(e) => updateLayer(selectedLayer.id, { fontStyle: e.target.value as 'bold' | 'normal' })}
                    className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg bg-white"
                  >
                    <option value="bold">Жирный</option>
                    <option value="normal">Обычный</option>
                  </select>
                </div>
              </div>
            </div>
          )}
                    <div className="space-y-3 pt-3 border-t border-slate-200">
            <div className="text-xs font-bold text-slate-700 uppercase">Размер слайда (px) и Логотип</div>
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(CANVAS_PRESETS) as Array<Exclude<CanvasAspectPreset, 'custom'>>).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => handleSelectAspect(key)}
                  className={`px-2.5 py-1 text-xs font-medium rounded border cursor-pointer ${
                    aspectPreset === key ? 'bg-slate-900 text-white border-slate-900' : 'bg-slate-50 text-slate-700 border-slate-300'
                  }`}
                >
                  {CANVAS_PRESETS[key].label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                min={300}
                max={4096}
                value={canvasW}
                onChange={(e) => { setAspectPreset('custom'); setCanvasW(Math.max(300, Number(e.target.value) || 1080)); }}
                className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg"
                title="Ширина холста (px)"
              />
              <input
                type="number"
                min={300}
                max={4096}
                value={canvasH}
                onChange={(e) => { setAspectPreset('custom'); setCanvasH(Math.max(300, Number(e.target.value) || 1080)); }}
                className="px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg"
                title="Высота холста (px)"
              />
            </div>

            <div className="flex items-center justify-between gap-2 pt-1">
              <input ref={logoFileInputRef} type="file" accept="image/*" onChange={handleUploadLogoFile} className="hidden" />
              <button
                type="button"
                onClick={() => logoFileInputRef.current?.click()}
                className="px-3 py-1.5 text-xs font-semibold bg-slate-100 text-slate-800 border border-slate-300 rounded-lg hover:bg-slate-200 cursor-pointer"
              >
                {brandLogo.url ? 'Заменить логотип' : 'Загрузить логотип (PNG/SVG)'}
              </button>
              {brandLogo.url && (
                <select
                  value={brandLogo.position}
                  onChange={(e) => setBrandLogo((p) => ({ ...p, position: e.target.value as BrandLogoConfig['position'] }))}
                  className="px-2 py-1.5 text-xs border border-slate-300 rounded-lg bg-white"
                >
                  <option value="top-left">Слева вверху</option>
                  <option value="top-right">Справа вверху</option>
                  <option value="bottom-left">Слева внизу</option>
                  <option value="bottom-right">Справа внизу</option>
                </select>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
