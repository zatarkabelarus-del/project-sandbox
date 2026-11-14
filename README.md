# AI PicChanger+SEO

Мультиплатформенная браузерно-серверная платформа с мультиагентным ИИ-оркестром для автоматизированного создания продающих карточек товаров, редактируемой инфографики, рич-контента и комплексной SEO-оптимизации каталогов e-commerce.

## Структура проекта
- `frontend/` — клиентское SPA-приложение (React 18 + Vite 6 + TypeScript + Tailwind CSS v4 + react-konva).
- `backend/` — серверное ядро (FastAPI + ИИ-оркестратор + FSM + коннекторы CMS).
- `wordpress_bridge/` — лёгкий PHP-плагин для расширения REST API WooCommerce.
- `tests/` — изолированные верификационные автотесты.

## Быстрый старт (контур `DEV_MOCK`)

### 1. Запуск Backend
```bash
cd backend
py -3.13 -m venv .venv   # или py -3.14 -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
APP_MODE=DEV_MOCK uvicorn main:app --reload --port 8000
```

### 2. Запуск Frontend
```bash
cd frontend
npm install
npm run dev
```
