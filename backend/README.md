# Backend

FastAPI application for InsightFlow AI.

## Responsibility

HTTP API, configuration, logging, dataset upload, automatic profiling, intent detection, and orchestration of specialized engines.

## Layout

| Path | Purpose | Introduced |
|------|---------|------------|
| `app/main.py` | FastAPI entrypoint | Phase 1 |
| `app/api/` | Route handlers | Phase 1 |
| `app/core/` | Config, logging | Phase 1 |
| `app/schemas/` | Request/response models | Phase 2 |
| `app/services/` | Upload, profiling, intent services | Phase 2–4 |
| `app/utils/` | Shared helpers | Phase 1+ |
| `app/engines/intent/` | Rule-based intent detection | Phase 4 |
| `app/engines/` | Analytics, viz, ML, RAG, insight | Phases 5–10 |
| `data/` | Uploads and processed artifacts | Phase 2 |
| `models/` | Persisted ML artifacts | Phase 9 |
| `tests/` | Backend tests | Phase 1+ |

## Setup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
cp ../.env.example ../.env
```

On some Windows machines `pip.exe` is blocked by Application Control — use `python -m pip` instead.

## Run

From the `backend/` directory:

```bash
python -m uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000 in the browser (not `http://0.0.0.0:8000`).

- API root: http://127.0.0.1:8000/
- Health: http://127.0.0.1:8000/api/v1/health
- Upload: `POST /api/v1/datasets/upload` (multipart field `file`)
- Profile: `GET /api/v1/datasets/{dataset_id}/profile`
- Refresh profile: `POST /api/v1/datasets/{dataset_id}/profile`
- Intent detect: `POST /api/v1/intent/detect`
- Intent catalog: `GET /api/v1/intent/catalog`
- Analytics query: `POST /api/v1/analytics/query`
- Visualization chart: `POST /api/v1/visualization/chart`
- RAG index: `POST /api/v1/rag/index`
- RAG query: `POST /api/v1/rag/query`
- RAG status: `GET /api/v1/rag/{dataset_id}/status`
- ML run: `POST /api/v1/ml/run` (`forecast` | `segmentation` | `anomaly`)
- Insight analyze: `POST /api/v1/insight/analyze` (`explanation` | `recommendation` | `root_cause`)
- Docs: http://127.0.0.1:8000/docs

### Supported upload types

| Extension | Type |
|-----------|------|
| `.csv` | CSV |
| `.xlsx` | Excel |
| `.pdf` | PDF (auto-indexed for RAG) |

Uploads are profiled automatically (rows, columns, missing values, duplicates, statistics).
PDF uploads are also chunked and indexed into FAISS for document QA.
Tabular uploads support analytics, charts, ML tasks, and business insights.

## Test

```bash
cd backend
python -m pytest -q
```

## Status

Phase 10 complete: Insight Engine builds processed evidence (profile/KPIs/segments/ML)
then explains, recommends, or root-causes — Groq only for synthesis when enabled.
Intent routing marks all engines through `insight` as ready.
Phase 11 will cover deployment (Vercel / AWS EC2 / Nginx).
