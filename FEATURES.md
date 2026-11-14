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

## Сессия 3: Слой БД (SQLAlchemy), Графический движок, Оркестратор агентов и Коннекторы CMS — [ПЛАН]
- [ ] Асинхронные модели БД (`backend/database/models.py`, `session.py`) и фоновый обработчик серий с чекпоинтами (`backend/workers/batch_processor.py`).
- [ ] Мультиагентный ИИ-оркестр (`vision_analyst.py`, `marketer.py`, `scene_designer.py`, `layout_engine.py`, `critic.py`, `style_factory.py`) и внешние конфиги `backend/configs/`.
- [ ] Графический движок (`backend/graphics/image_utils.py`) с контролем RAM (`del + gc.collect()`).
- [ ] Коннекторы (`base_connector.py`, `woocommerce.py`, `excel_csv_importer.py`) и связка фронтенда (`frontend/src/api/client.ts`) с живым Backend API.
