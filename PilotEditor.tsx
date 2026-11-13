import React, { useEffect, useRef, useState } from 'react';
import { Stage, Layer, Rect, Text, Group, Image as KonvaImage } from 'react-konva';
import Konva from 'konva';
import { CheckCircle, Download, Plus, Trash2, Layers, Sparkles, Send } from 'lucide-react';
import { CanvasLayerItem, ProductItem } from '../../types/schema';
import { useTranslation } from '../../i18n/LanguageContext';
import { apiClient } from '../../api/client';

interface PilotEditorProps {
  product: ProductItem;
  onApprovePilot: (productId: string, updatedProduct: ProductItem) => void;
}

const useLoadedImage = (url: string) => {
  const = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!url) return;
    const img = new window.Image();
    img.crossOrigin = 'anonymous';
    img.src = url;
    img.onload = () => setImage(img);
  }, [url]);
  return image;
};

export const PilotEditor: React.FC<PilotEditorProps> = ({ product, onApprovePilot }) => {
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
  const [backendTaskId, setBackendTaskId] = useState<number | null>(null);
  const [backendProductId, setBackendProductId] = useState<number>(1);
  const [statusBanner, setStatusBanner] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setSlides(initialSlides);
    setActiveSlideIdx(0);
    setSelectedLayerId(initialSlides.at(0)?.layers.at(0)?.id || null);
    setStatusBanner(null);
  }, [product.id]);

  const currentSlide = slides.at(activeSlideIdx) || slides.at(0)!;
  const bgImage = useLoadedImage(currentSlide.backgroundUrl);
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

  const handleExportWebP = () => {
    if (!stageRef.current) return;
    const dataUrl = stageRef.current.toDataURL({ mimeType: 'image/webp', quality: 0.92 });
    const link = document.createElement('a');
    link.download = `${product.sku}-slide-${currentSlide.slideIndex}.webp`;
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
        lang,
      });
      if (typeof res.task_id === 'number') setBackendTaskId(res.task_id);
      if (typeof res.db_product_id === 'number') setBackendProductId(res.db_product_id);
      setStatusBanner(`FSM: ${String(res.fsm_status_label || res.fsm_status || 'PILOT_REVIEW')}`);
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
        preview_only: true,
        lang,
      });
      const mediaCount = Array.isArray(res.media_plan) ? res.media_plan.length : 0;
      setStatusBanner(`Предпросмотр CMS готов: подготовлено ${mediaCount} SEO-медиафайлов и HTML-блок.`);
    } catch (err) {
      setStatusBanner(err instanceof Error ? err.message : 'Ошибка предпросмотра CMS');
    } finally {
      setIsLoading(false);
    }
  };

  const handleApprove = async () => {
    const bakedPreview = stageRef.current
      ? stageRef.current.toDataURL({ mimeType: 'image/webp', quality: 0.9 })
      : product.generatedPreviewUrl;

    try {
      const approved = await apiClient.approvePilotTemplate({
        name: `Pilot-${product.sku}`,
        pilot_product_id: backendProductId,
        style_code: 'minimal_light',
        approved_layout_schema: { slides },
      });
      localStorage.setItem('ai_pilot_template_id', String(approved.pilot_template_id));
      setStatusBanner(`Эталон #${approved.pilot_template_id} утверждён для серии.`);
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
          <button
            onClick={handleGeneratePilotAI}
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-lg hover:bg-indigo-100 cursor-pointer"
          >
            <Sparkles className="w-4 h-4" />
            Сгенерировать ИИ-Пилот
          </button>

          <button
            onClick={handleExportWebP}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium bg-white border border-slate-300 rounded-lg hover:bg-slate-50 text-slate-700 cursor-pointer"
          >
            <Download className="w-4 h-4" />
            {t('pilot.export_webp')}
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
            <Stage ref={stageRef} width={560} height={560} scaleX={0.7} scaleY={0.7}>
              <Layer>
                <Rect x={0} y={0} width={800} height={800} fill="#f8fafc" />
                {bgImage && <KonvaImage image={bgImage} x={0} y={0} width={800} height={800} />}
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
                      onDragEnd={(e) => {
                        updateLayer(layer.id, {
                          x: Math.round(e.target.x()),
                          y: Math.round(e.target.y()),
                        });
                      }}
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
                        fontSize={layer.fontSize}
                        fontStyle="bold"
                        align="center"
                        verticalAlign="middle"
                        padding={10}
                      />
                    </Group>
                  );
                })}
              </Layer>
            </Stage>
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
