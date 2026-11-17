# Реестр реализованных возможностей (FEATURES)

## Сессия 1: Frontend SPA (UI-First, контур DEV_MOCK) — [ГОТОВО]
- [x] **CatalogManager**: очередь задач, фильтрация по статусам FSM, 3 канала онбординга (CMS REST API, Excel/CSV, прямая загрузка фото), пакетный запуск серии.
- [x] **PilotEditor**: двухслойный Canvas-редактор (`react-konva`) с разделением растрового фона и векторного JSON-слоя инфографики, экспорт в WebP и утверждение эталона.
- [x] **StorefrontPreview**: симулятор витрины («Карточка товара До/После» и «Сетка категории»).
- [x] **RichSeoWorkspace**: генерация и редактирование SEO-метаданных (товары, медиафайлы, категории) и изолированного HTML рич-контента.
- [x] **SettingsPanel**: выбор адаптера CMS, маскирование ключей (Zero-Frontend Secrets), финансовый лимитер бюджета и управление ИИ-агентами.
- [x] **i18n**: мгновенное переключение языков интерфейса (`RU` / `EN`).

## Сессия 2: Системное ядро Backend (FastAPI) и контур DEV_MOCK — [ГОТОВО]
- [x] **Инвариантная точка входа** (`backend/main.py`): управление режимами через `APP_MODE` (`DEV_MOCK` по умолчанию), настройка CORS и локализованный обработчик ошибок.
- [x] **Системное ядро** (`backend/core/`): `config.py` (строго абсолютные пути), `exceptions.py` (кастомная иерархия ошибок), `security.py` (AES-256 через Fernet и маскирование ключей), `fsm.py` (конечный автомат с циклом «Пилот ➔ Серия»), `budget_limiter.py` (дневной финансовый предохранитель), `i18n.py`.
- [x] **Локализация и SEO-шаблоны** (`backend/locales/`): `ru.json`, `en.json`, `seo_templates.json`.
- [x] **Слой ИИ-провайдеров** (`backend/agents/providers/`): абстрактный интерфейс `AIProviderAdapter`, мгновенный `MockAIProvider` и фабрика `factory.py`.
- [x] **Верификация** (`tests/test_session1_core.py`): 4/4 автотеста успешно пройдены в контуре `DEV_MOCK`.

## Сессия 3: Слой БД (SQLAlchemy), Графический движок, Оркестратор агентов и Коннекторы CMS — [ГОТОВО]
- [x] **Асинхронные модели БД** (`backend/database/models.py`, `session.py`): модели `Store`, `Product`, `VisualStyle`, `PilotTemplate`, `GenerationTask`, `AuditLog` с поддержкой SQLite (`aiosqlite`) и PostgreSQL (`asyncpg`).
- [x] **Фоновый обработчик серий** (`backend/workers/batch_processor.py`): чекпоинты шагов, изоляция сбоев отдельных товаров и Retry Policy (2, 4, 8 сек).
- [x] **Мультиагентный ИИ-оркестр** (`backend/agents/`): `vision_analyst.py` (тумблер `enable_vision`), `marketer.py`, `scene_designer.py`, `layout_engine.py`, `critic.py`, `style_factory.py` и внешние конфиги `backend/configs/`.
- [x] **Графический движок** (`backend/graphics/image_utils.py`): нормализация холста `1080x1440`, контроль WCAG 2.1 (`>= 4.5`) и BBox (`<= 0.05`), контроль RAM (`del + gc.collect()`).
- [x] **Коннекторы и связка с UI**: `base_connector.py`, `woocommerce.py`, `excel_csv_importer.py`, `frontend/src/api/client.ts` и тест `tests/test_session3_pipeline.py`.

## Сессия 4: Боевые шлюзы CLOUD_API, GPU_SERVER с автостопом и WP Bridge — [ГОТОВО]
- [x] **Облачный провайдер** (`backend/agents/providers/cloud_provider.py`): универсальный OpenAI-совместимый клиент (`httpx`) с расшифровкой ключей из `SecretVault` (AES-256) и контролем бюджета `BudgetLimiter`.
- [x] **Выделенный GPU-сервер** (`backend/agents/providers/gpu_server_provider.py`): инференс Open-Source моделей (Flux, Qwen-VL, RMBG-2.0) и фоновый watchdog-таймер автостопа.
- [x] **WordPress Bridge и публикация** (`wordpress_bridge/ai-catalog-bridge.php`, `backend/routes_publish.py`): гибридная авторизация (Application Passwords + `X-Bridge-Auth`), загрузка медиа с SEO-атрибутами и тест `tests/test_session4_integration.py`.

## Сессия 5: Store CRUD API, Синхронизация каталога, Защита шорткодов/видео и SEO категорий — [ГОТОВО]
- [x] **Store CRUD API** (`backend/routes_store_seo.py`, `backend/connectors/store_service.py`): хранение кредов магазинов в зашифрованном виде AES-256, частичное обновление без затирания секретов.
- [x] **Гибридная защита встраиваемых блоков** (`backend/connectors/content_protector.py`, `SeoDashboard.tsx`): 4 правила размещения вокруг существующих шорткодов и видео, суффикс магазина и `video_url`.
- [x] **Синхронизация каталога и SEO категорий**: массовая выгрузка товаров, генерация и публикация SEO-текстов категорий и тест `tests/test_session5_sync.py`.

## Сессия 6: Мультиформатный экспорт изображений и Финализация Релиза v1.0 — [ГОТОВО]
- [x] **Мультиформатный рендеринг** (`backend/graphics/image_utils.py`): поддержка WebP (`method=6`), прогрессивного JPEG (`subsampling="4:2:0"`), AVIF (с авто-откатом на WebP при отсутствии `libavif`) и PNG (`compress_level=9`) с выбором качества (40–100%).
- [x] **Плагин WP Bridge v1.1.0**: расширена поддержка `upload_mimes` для WebP, JPEG, AVIF и PNG.
- [x] **Верификация Релиза v1.0**: сквозной тест `tests/test_session6_release.py` (15/15 автотестов) и протокол безопасной проверки на скрытом товаре-черновике.

## Сессия 7: Активация WP Bridge, Неблокирующая фоновая очередь и Production Docker — [ГОТОВО]
- [x] **Активация WP Bridge на боевом сайте**: плагин `ai-catalog-bridge.php` v1.1.0 установлен и проверен на полигоне WordPress / WooCommerce (`zatarka.by`).
- [x] **Неблокирующая фоновая очередь задач** (`BatchJob` в `models.py`, `run_batch_job_background` в `batch_processor.py`, эндпоинты `/api/batch/run`, `/api/batch/status/{job_id}`, `/api/batch/active`, `/api/batch/cancel/{job_id}`): поллинг прогресса каждые 1.5 сек и живой прогресс-бар в `CatalogManager.tsx` с возможностью остановки.
- [x] **Production Docker-сборка**: `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `.dockerignore`, обновлённый `docker-compose.yml` (PostgreSQL, Redis, Backend, Frontend Nginx) и тест `tests/test_session7_queue.py` (16/16 автотестов).

## Сессия 8: Локальная доработка дизайн-студии, лендинг товара и SaaS-модуль (Auth + Токен-биллинг) — [ПЛАН]
- [ ] **Регистрация пользователей и токен-биллинг**: регистрация/вход (JWT), изоляция данных по `user_id`, приветственный пакет бесплатных тестовых токенов, журнал транзакций, экран «Баланс и тарифы» и базовая админ-панель.
- [ ] **Локальные графические утилиты (`backend/graphics/bg_remover.py`)**: удаление фона на CPU (`rembg` / `U2Net`), нарезка и умный ресайз.
- [ ] **Расширенный редактор слоев (`PilotEditor`)**: стандартные и ручные размеры слайдов, библиотека собственных фонов, загрузка и позиционирование логотипа бренда, выбор шрифтов и начертаний.
- [ ] **Конструктор лендинг-страницы товара (`LandingBuilder`)**: отдельная вкладка генерации и сборки мини-лендинга товара с экспортом в изолированный HTML или серию слайдов.
- [ ] **UI/UX улучшения** по результатам живого тестирования программы на локальном ПК.
