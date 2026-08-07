# Frontend

React + Vite + TailwindCSS + Axios client for InsightFlow AI.

## Responsibility

Dashboard workspace for:

- Dataset upload (CSV / Excel / PDF)
- Intent-driven chat queries
- Plotly chart rendering
- Analytics / profile results

## Setup

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173

Backend must be running on http://127.0.0.1:8000 (Vite proxies `/api` there).

Optional env:

```bash
# frontend/.env
VITE_API_BASE_URL=/api/v1
```

## Build

```bash
npm run build
npm run preview
```

## Status

Phase 7 complete: dashboard, upload, chat, and charts are wired to the Phase 0–6 backend.
