# InsightFlow AI — Phases 0–10 Implementation Report

**Product:** InsightFlow AI — modular AI Business Intelligence platform  
**Status:** Phases 0–10 complete · App version `0.10.0` · Phase 11 (deployment) pending  
**Philosophy:** Intent → Engine → LLM only when reasoning is required (not an LLM wrapper)

---

## 1. System overview

```
User (React dashboard)
        ↓
Upload CSV / Excel / PDF  →  Profile dataset
        ↓
Ask a question in chat
        ↓
Intent Detection (rules + LangGraph/Groq + session memory)
        ↓
Route to specialized engine
        ├── Analytics (Pandas KPIs / aggregates)
        ├── Visualization (Plotly charts)
        ├── RAG (PDF chunk → FAISS → answer)
        ├── ML (forecast / segmentation / anomaly)
        └── Insight (explanation / recommendation / root cause)
        ↓
Results + Chart panels
```

| Query type | Engine | LLM? |
|------------|--------|------|
| Totals, filters, lowest/highest | Analytics | No |
| Bar / line / pie / scatter | Visualization | No |
| PDF / document QA | RAG | Optional (Groq) |
| Forecast, clusters, outliers | ML | No |
| Why / recommend / explain | Insight | Preferred (Groq), deterministic fallback |

---

## 2. Tech stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, Vite 6, Tailwind CSS, Axios, Plotly |
| Backend | FastAPI, Uvicorn, Pydantic Settings |
| Orchestration | LangGraph + MemorySaver |
| LLM | Groq (`llama-3.3-70b-versatile`) |
| Analytics | Pandas, NumPy |
| Visualization | Plotly |
| RAG | pypdf, hashed embeddings, FAISS |
| ML | scikit-learn |
| Config | `.env` / `.env.example` |
| Tests | pytest + FastAPI TestClient |

**API prefix:** `/api/v1`

---

## 3. How the stack was built (end-to-end)

Implementation followed `PROJECT_CONSTITUTION.md`: one phase at a time, leave the app runnable, do not redesign unrelated modules.

1. **Scaffold** the monorepo (`backend/`, `frontend/`, `deployment/`) and governing docs.  
2. **Stand up FastAPI** with config, logging, health, CORS.  
3. **Accept uploads** (CSV / Excel / PDF) into a dataset registry on disk.  
4. **Profile** each upload automatically (rows, columns, missing, duplicates, stats).  
5. **Detect intent** with rules + optional Groq/LangGraph; ground entities to real columns; add session memory for follow-ups.  
6. **Analytics** engine for deterministic aggregations/KPIs.  
7. **Visualization** engine for Plotly charts.  
8. **React dashboard** that uploads data, chats, calls intent, then the matching engine.  
9. **RAG** for PDFs (chunk → embed → FAISS → answer).  
10. **ML** for forecast / KMeans / IsolationForest.  
11. **Insight** engine for explanation / recommendation / root cause from evidence packs.  
12. **Polish** UX (two-page layout, dataset drawer, memory, closings) without changing engine contracts.

Local run (typical):

```bash
# Backend
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy ..\.env.example ..\.env      # set GROQ_API_KEY if using LLM
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev                       # http://127.0.0.1:5173  (proxies /api → :8000)
```

---

## 4. Phase-by-phase report

### Phase 0 — Project Foundation

**Objective**  
Create a production-shaped repository layout, constitution, ignore rules, and env template so later phases have a stable home.

**Step-by-step**
1. Define engineering rules in `PROJECT_CONSTITUTION.md` (hybrid AI, modular engines, incremental phases).  
2. Create root README, `.gitignore`, `.env.example`.  
3. Create empty `backend/`, `frontend/`, `deployment/` trees.  
4. Document intended hosts (Vercel frontend, EC2 + Nginx backend) without implementing deploy yet.

**Files**

| File | Summary |
|------|---------|
| `PROJECT_CONSTITUTION.md` | Governing architecture, philosophy, and phase roadmap |
| `README.md` | Product overview, stack table, phase status, getting started |
| `.gitignore` | Ignores venv, `node_modules`, `.env`, uploads, models, caches |
| `.env.example` | Template for API, Groq, paths, RAG, ML, Insight settings |
| `deployment/README.md` | Placeholder for Phase 11 deployment notes |
| `backend/README.md` | Backend-focused docs (grows with phases) |
| `frontend/README.md` | Frontend-focused docs (Phase 7+) |

---

### Phase 1 — Backend Foundation

**Objective**  
Runnable FastAPI application with configuration, structured logging, health check, and package layout for engines/services.

**Step-by-step**
1. Add `requirements.txt` (FastAPI, Uvicorn, Pydantic Settings, pytest, httpx).  
2. Implement `Settings` from environment variables.  
3. Configure logging and app lifespan (ensure data directories exist).  
4. Mount API router under `/api/v1`; expose `GET /` and `GET /health`.  
5. Enable CORS for local Vite origin.  
6. Add health + config tests.

**Files**

| File | Summary |
|------|---------|
| `backend/requirements.txt` | Backend dependencies (extends through Phase 10) |
| `backend/app/main.py` | FastAPI entrypoint, lifespan, CORS, root index |
| `backend/app/api/router.py` | Aggregates all route modules |
| `backend/app/api/routes/health.py` | Liveness/health response |
| `backend/app/core/config.py` | Env-driven settings (`API_*`, `GROQ_*`, paths, feature flags) |
| `backend/app/core/logging.py` | Central logging setup |
| `backend/app/api/__init__.py` | API package marker |
| `backend/app/core/__init__.py` | Core package marker |
| `backend/app/engines/__init__.py` | Engines package stub |
| `backend/app/services/__init__.py` | Services package stub |
| `backend/app/utils/__init__.py` | Utils package stub |
| `backend/tests/test_health.py` | Health endpoint tests |
| `backend/tests/test_config.py` | Settings/config tests |

**API**
- `GET /`
- `GET /api/v1/health`

---

### Phase 2 — Dataset Upload (CSV / Excel / PDF)

**Objective**  
Accept business files, validate type/size, persist on disk, and expose list/get/delete.

**Step-by-step**
1. Define Pydantic schemas for dataset metadata.  
2. Implement safe file helpers and CSV/Excel readers (encoding fallbacks).  
3. Build `DatasetService`: generate `dataset_id`, store under `data/uploads/{id}/`, write `meta.json`.  
4. Expose multipart `POST /datasets/upload` plus list/get/delete.  
5. Reject unsupported types and oversize uploads.  
6. Add dataset API tests.

**Files**

| File | Summary |
|------|---------|
| `backend/app/api/routes/datasets.py` | Upload, list, get, delete (+ profile routes in Phase 3) |
| `backend/app/services/dataset_service.py` | Registry, storage, load DataFrame, later hooks for profile/RAG |
| `backend/app/schemas/dataset.py` | Upload/list/meta response models |
| `backend/app/utils/files.py` | Safe paths, size checks |
| `backend/app/utils/csv_io.py` | Encoding-aware CSV/Excel IO |
| `backend/data/uploads/` | Runtime storage for originals |
| `backend/data/processed/` | Runtime storage for profiles/artifacts |
| `backend/tests/test_datasets.py` | Upload/list/get/delete tests |

**API**
- `POST /api/v1/datasets/upload`
- `GET /api/v1/datasets`
- `GET /api/v1/datasets/{dataset_id}`
- `DELETE /api/v1/datasets/{dataset_id}`

---

### Phase 3 — Automatic Dataset Profiling

**Objective**  
On upload (and on demand), understand structure: row/column counts, dtypes, missing values, duplicates, column stats, PDF metadata.

**Step-by-step**
1. Define profile schemas (`columns`, stats, metadata).  
2. Implement `ProfilingService` for tabular frames and PDF page metadata.  
3. Persist `{dataset_id}.profile.json` under `data/processed/`.  
4. Hook auto-profile into upload success path.  
5. Expose `GET` + `POST` (refresh) profile routes.  
6. Add profiling tests.

**Files**

| File | Summary |
|------|---------|
| `backend/app/services/profiling_service.py` | Builds and persists dataset profiles |
| `backend/app/schemas/profile.py` | Profile response models |
| `backend/app/api/routes/datasets.py` | Profile endpoints (shared with Phase 2) |
| `backend/data/processed/*.profile.json` | Persisted profile artifacts |
| `backend/tests/test_profiling.py` | Profiling behavior tests |

**API**
- `GET /api/v1/datasets/{dataset_id}/profile`
- `POST /api/v1/datasets/{dataset_id}/profile`

---

### Phase 4 — Intent Detection

**Objective**  
Classify each user question into an intent/engine (`analytics`, `visualization`, `ml`, `rag`, `insight`, `profile`, `unknown`) with grounded entities and session memory.

**Step-by-step**
1. Define intent schemas + catalog of supported intents.  
2. Implement rule-based keyword detector (offline fallback).  
3. Implement Groq LLM detector with strict JSON entity schema.  
4. Build LangGraph flow:  
   `load_context → load_memory → classify → apply_memory → ground_entities → route → save_memory`  
5. Ground metrics/dimensions/filters to real column names.  
6. Add in-session memory (follow-ups, closings, history recall) via store + LangGraph `MemorySaver`.  
7. Expose `POST /intent/detect` and `GET /intent/catalog`.  
8. Extensive intent/memory tests.

**Files**

| File | Summary |
|------|---------|
| `backend/app/api/routes/intent.py` | Detect + catalog HTTP endpoints |
| `backend/app/services/intent_service.py` | Builds detector, invokes graph, maps API response |
| `backend/app/schemas/intent.py` | Request/response, routing, session_id, reply |
| `backend/app/engines/intent/base.py` | Detector protocol + `IntentMatch` |
| `backend/app/engines/intent/rule_based.py` | Deterministic keyword classifier |
| `backend/app/engines/intent/llm_based.py` | Groq classifier with rules fallback |
| `backend/app/engines/intent/rules.py` | Keyword rules, catalog, engine routing metadata |
| `backend/app/engines/intent/graph.py` | LangGraph orchestration + MemorySaver |
| `backend/app/engines/intent/prompts.py` | System/user prompts for Groq intent |
| `backend/app/engines/intent/memory.py` | Session store, follow-ups, closings, entity enrich |
| `backend/app/engines/intent/entity_grounding.py` | Resolve entities to schema columns; measure vs dimension |
| `backend/app/engines/intent/__init__.py` | Public exports |
| `backend/tests/test_intent.py` | Routing, memory, closings, grounding tests |

**API**
- `POST /api/v1/intent/detect` (body: `query`, optional `dataset_id`, `session_id`)
- `GET /api/v1/intent/catalog`

**Memory behaviors (later polish)**
- Follow-ups (`what about profit`) resume topic and update entities.  
- Unknown / gibberish → short reply, no engine.  
- Closings (`bye`, `bai`, `fine`, `thanks`) → polite close + clear active topic.  
- History (`what did I ask previously`) → list prior asks.  
- Explicit chart asks stay visualization.

---

### Phase 5 — Analytics Engine

**Objective**  
Deterministic Pandas analytics: filter → aggregate → sort → limit → KPIs. No LLM.

**Step-by-step**
1. Define analytics request/response schemas (metrics, dimensions, filters, aggregations, sort).  
2. Implement `AnalyticsEngine` with column resolution and numeric coercion for string KPIs.  
3. Wrap with `AnalyticsService` (load dataset → execute).  
4. Expose `POST /analytics/query`.  
5. Add aggregation/filter/sort tests.

**Files**

| File | Summary |
|------|---------|
| `backend/app/api/routes/analytics.py` | Analytics query endpoint |
| `backend/app/services/analytics_service.py` | Loads frame and runs engine |
| `backend/app/engines/analytics/engine.py` | Pandas filter/aggregate/sort/KPI logic |
| `backend/app/engines/analytics/__init__.py` | Package marker |
| `backend/app/schemas/analytics.py` | Query/response models |
| `backend/app/utils/dataframe.py` | `ensure_numeric_series` for object-dtype KPIs |
| `backend/tests/test_analytics.py` | Analytics engine/API tests |

**API**
- `POST /api/v1/analytics/query`

---

### Phase 6 — Visualization Engine

**Objective**  
Build interactive Plotly charts (bar, line, pie, scatter) from the same grounded entity style as analytics.

**Step-by-step**
1. Define visualization schemas (`chart_type`, metrics, dimensions, filters, title).  
2. Implement Plotly figure builder with aggregation + optional sort for extremes.  
3. Wrap with visualization service.  
4. Expose `POST /visualization/chart`.  
5. Add chart tests.

**Files**

| File | Summary |
|------|---------|
| `backend/app/api/routes/visualization.py` | Chart creation endpoint |
| `backend/app/services/visualization_service.py` | Loads data and runs viz engine |
| `backend/app/engines/visualization/engine.py` | Plotly figure construction |
| `backend/app/engines/visualization/__init__.py` | Package marker |
| `backend/app/schemas/visualization.py` | Chart request/response models |
| `backend/tests/test_visualization.py` | Visualization tests |

**API**
- `POST /api/v1/visualization/chart`

---

### Phase 7 — React Frontend

**Objective**  
Dashboard: upload datasets, view profile, chat with intent routing, show results and charts.

**Step-by-step**
1. Scaffold Vite + React + Tailwind.  
2. Configure Vite proxy `/api` → `http://127.0.0.1:8000`.  
3. Build Axios client for all backend endpoints.  
4. Implement `queryRouter` to map intent entities → engine payloads.  
5. Build UI: dataset drawer, chat, results, charts, profile card.  
6. Wire chat flow: detect intent → call matching engine → summarize answer (including extreme “lowest/highest”).  
7. Add session id for conversation memory; two-page layout (Results+Chat / Visualization).

**Files**

| File | Summary |
|------|---------|
| `frontend/package.json` | Scripts and deps (React, Vite, Tailwind, Axios, Plotly) |
| `frontend/vite.config.js` | Dev server + `/api` proxy |
| `frontend/tailwind.config.js` | Tailwind theme/content paths |
| `frontend/postcss.config.js` | PostCSS pipeline |
| `frontend/index.html` | HTML shell |
| `frontend/src/main.jsx` | React mount |
| `frontend/src/index.css` | Global + Tailwind styles |
| `frontend/src/App.jsx` | Orchestration: session, chat, engine dispatch, layout |
| `frontend/src/api/client.js` | Axios wrappers for all `/api/v1/*` calls |
| `frontend/src/lib/queryRouter.js` | Intent → analytics/viz/ML/insight payloads + extreme answers |
| `frontend/src/components/DatasetPanel.jsx` | Upload, list, select, delete datasets |
| `frontend/src/components/ChatPanel.jsx` | Chat transcript + input |
| `frontend/src/components/ResultsPanel.jsx` | Intent meta, KPIs, tables, RAG/ML/insight blocks |
| `frontend/src/components/ChartPanel.jsx` | Plotly chart renderer |
| `frontend/src/components/ProfileCard.jsx` | Human-readable profile summary |

**Backend APIs used:** Phases 1–10 (no new routes in this phase).

---

### Phase 8 — RAG (PDF Search / Document QA)

**Objective**  
Answer questions over uploaded PDFs without dumping full documents into the LLM.

**Step-by-step**
1. Chunk PDF text deterministically.  
2. Build offline hashed n-gram embeddings (no paid embedding API required).  
3. Persist FAISS index per dataset under `data/rag/`.  
4. Retrieve top-k chunks; optionally synthesize answer with Groq.  
5. Auto-index on PDF upload; expose index/status/query APIs.  
6. Frontend routes `rag` intent to `POST /rag/query`.  
7. Add RAG tests.

**Files**

| File | Summary |
|------|---------|
| `backend/app/api/routes/rag.py` | Index, status, query endpoints |
| `backend/app/services/rag_service.py` | App service + upload auto-index hook |
| `backend/app/engines/rag/engine.py` | End-to-end retrieve → answer pipeline |
| `backend/app/engines/rag/chunking.py` | Text splitter with overlap |
| `backend/app/engines/rag/embeddings.py` | Local hashed embeddings |
| `backend/app/engines/rag/store.py` | FAISS persistence / load |
| `backend/app/engines/rag/prompts.py` | Grounded answer prompts |
| `backend/app/engines/rag/__init__.py` | Package marker |
| `backend/app/schemas/rag.py` | RAG request/response models |
| `backend/data/rag/` | Runtime index artifacts |
| `backend/tests/test_rag.py` | RAG pipeline/API tests |

**API**
- `POST /api/v1/rag/index`
- `GET /api/v1/rag/{dataset_id}/status`
- `POST /api/v1/rag/query`

---

### Phase 9 — Machine Learning

**Objective**  
Train/infer on demand for forecast, customer segmentation, and anomaly detection; return summaries + optional Plotly figures.

**Step-by-step**
1. Define ML schemas (`task`, target, horizon, clusters, contamination).  
2. Implement task modules: seasonal-naive/trend forecast, KMeans, IsolationForest.  
3. Central `MLEngine` router + helpers for column picks.  
4. Persist lightweight artifacts under `models/`.  
5. Expose `POST /ml/run`.  
6. Frontend maps ML intents and renders charts when present.  
7. Add ML tests.

**Files**

| File | Summary |
|------|---------|
| `backend/app/api/routes/ml.py` | `POST /ml/run` |
| `backend/app/services/ml_service.py` | Loads data and runs ML engine |
| `backend/app/engines/ml/engine.py` | Task router |
| `backend/app/engines/ml/forecast.py` | Time-series forecast |
| `backend/app/engines/ml/segmentation.py` | KMeans segmentation |
| `backend/app/engines/ml/anomaly.py` | IsolationForest anomalies |
| `backend/app/engines/ml/helpers.py` | Shared feature/target helpers |
| `backend/app/engines/ml/__init__.py` | Package marker |
| `backend/app/schemas/ml.py` | ML request/response models |
| `backend/models/` | Runtime ML artifacts |
| `backend/tests/test_ml.py` | ML task tests |

**API**
- `POST /api/v1/ml/run` — `forecast` | `segmentation` | `anomaly`

---

### Phase 10 — Business Insight Engine

**Objective**  
Produce business explanations, recommendations, and root-cause narratives from compact evidence packs (not raw CSVs).

**Step-by-step**
1. Build evidence packer (KPIs, top/bottom segments, optional ML context).  
2. Implement Groq synthesis prompts for three modes.  
3. Add deterministic fallback when Groq is off/unavailable.  
4. Expose `POST /insight/analyze`.  
5. Frontend routes insight intents and renders findings/recommendations.  
6. Add insight tests.

**Files**

| File | Summary |
|------|---------|
| `backend/app/api/routes/insight.py` | `POST /insight/analyze` |
| `backend/app/services/insight_service.py` | Loads data and runs insight engine |
| `backend/app/engines/insight/engine.py` | Orchestrates evidence + LLM/deterministic path |
| `backend/app/engines/insight/evidence.py` | Compact evidence packs for the LLM |
| `backend/app/engines/insight/deterministic.py` | Offline insight generation |
| `backend/app/engines/insight/prompts.py` | Insight synthesis prompts |
| `backend/app/engines/insight/__init__.py` | Package marker |
| `backend/app/schemas/insight.py` | Insight request/response models |
| `backend/tests/test_insight.py` | Insight API/engine tests |

**API**
- `POST /api/v1/insight/analyze` — modes: `explanation` | `recommendation` | `root_cause`

---

## 5. API map (Phases 1–10)

| Method | Path | Phase |
|--------|------|-------|
| GET | `/` | 1 |
| GET | `/api/v1/health` | 1 |
| POST | `/api/v1/datasets/upload` | 2 |
| GET | `/api/v1/datasets` | 2 |
| GET / DELETE | `/api/v1/datasets/{id}` | 2 |
| GET / POST | `/api/v1/datasets/{id}/profile` | 3 |
| POST | `/api/v1/intent/detect` | 4 |
| GET | `/api/v1/intent/catalog` | 4 |
| POST | `/api/v1/analytics/query` | 5 |
| POST | `/api/v1/visualization/chart` | 6 |
| POST | `/api/v1/rag/index` | 8 |
| GET | `/api/v1/rag/{id}/status` | 8 |
| POST | `/api/v1/rag/query` | 8 |
| POST | `/api/v1/ml/run` | 9 |
| POST | `/api/v1/insight/analyze` | 10 |

---

## 6. Request flow (chat example)

1. User uploads `SuperStore_Orders.csv` → Phase 2 + 3 (profile).  
2. User: “bar chart of sales by region” → Phase 4 intent=`visualization` → Phase 6 chart → Chart panel.  
3. User: “which region has lowest sales” → Phase 4 (memory-aware) intent=`analytics` → Phase 5 sorted aggregate → chat answer + results table.  
4. User: “why is Canada low?” → Phase 4 intent=`insight` → Phase 10 evidence + explanation.  
5. User: “bye” → Phase 4 closing reply; topic cleared; no engine run.

---

## 7. Testing inventory

| Test file | Phase |
|-----------|-------|
| `backend/tests/test_health.py` | 1 |
| `backend/tests/test_config.py` | 1 |
| `backend/tests/test_datasets.py` | 2 |
| `backend/tests/test_profiling.py` | 3 |
| `backend/tests/test_intent.py` | 4 |
| `backend/tests/test_analytics.py` | 5 |
| `backend/tests/test_visualization.py` | 6 |
| `backend/tests/test_rag.py` | 8 |
| `backend/tests/test_ml.py` | 9 |
| `backend/tests/test_insight.py` | 10 |

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

---

## 8. Deployment (free / free-tier options)

Phase 11 in the constitution targets Vercel + AWS EC2 + Nginx. Below are **practical free-tier paths** you can use for demos and portfolios without paying initially.

### 8.1 Recommended free split

| Piece | Free option | Notes |
|-------|-------------|-------|
| Frontend | **Vercel** Hobby | Static Vite build; set `VITE_API_BASE_URL` to backend URL |
| Backend | **Render** free web service *or* **Railway** trial *or* **Fly.io** free allowance | Runs Uvicorn; needs persistent disk for uploads if you want data to survive restarts |
| LLM | **Groq** free API tier | Set `GROQ_API_KEY`; rate limits apply |
| Embeddings / FAISS | Local (already in-app) | No third-party vector DB cost |
| Database | SQLite on disk (current) | Fine for demo; use managed Postgres later if needed |

Constitution target (when you leave free tier): Frontend **Vercel**, Backend **AWS EC2 + Nginx**.

---

### 8.2 Frontend on Vercel (free)

1. Build locally to verify:

```bash
cd frontend
npm install
npm run build
```

2. Add env for production API (create `frontend/.env.production` or Vercel env vars):

```env
VITE_API_BASE_URL=https://YOUR-BACKEND.onrender.com/api/v1
```

3. Ensure `frontend/src/api/client.js` uses `import.meta.env.VITE_API_BASE_URL` (or default `/api/v1` for local proxy only).

4. Deploy:
   - Import GitHub repo in [Vercel](https://vercel.com)
   - Root / framework: `frontend` · Build: `npm run build` · Output: `dist`
   - Add `VITE_API_BASE_URL`

5. CORS: allow your Vercel origin on the FastAPI backend.

---

### 8.3 Backend on Render (free tier)

1. Create a **Web Service** from the repo.  
2. Root directory: `backend`  
3. Build command:

```bash
pip install -r requirements.txt
```

4. Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

5. Environment variables (from `.env.example`):

| Variable | Example |
|----------|---------|
| `APP_ENV` | `production` |
| `DEBUG` | `false` |
| `GROQ_API_KEY` | your key |
| `INTENT_PROVIDER` | `llm` or `rules` |
| `UPLOAD_DIR` | `/var/data/uploads` |
| `PROCESSED_DIR` | `/var/data/processed` |
| `RAG_DIR` | `/var/data/rag` |
| `MODEL_DIR` | `/var/data/models` |
| `CORS` / allowed origins | your Vercel URL |

6. Attach a **persistent disk** (Render) for uploads/profiles/FAISS so free-tier restarts do not wipe demo data.  
7. Note: free web services **spin down** after idle; first request may be slow.

**Alternative free backends**
- **Railway:** similar Docker/Nixpacks deploy; watch trial credits.  
- **Fly.io:** `fly launch` + small VM; good for always-on small apps within free allowance.  
- **Hugging Face Spaces / Google Cloud Run:** possible with container; cold starts on free tiers.

---

### 8.4 Backend on AWS free tier (constitution-aligned)

When ready for Phase 11 style hosting:

1. Launch **EC2 t2.micro / t3.micro** (12‑month free tier for new accounts).  
2. Install Python 3.11+, nginx, optionally certbot.  
3. Clone repo, create venv, install `requirements.txt`.  
4. Run with systemd + Uvicorn (or Gunicorn+Uvicorn workers).  
5. Nginx reverse proxy:

```nginx
server {
  listen 80;
  server_name api.yourdomain.com;

  client_max_body_size 30M;

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
```

6. Point frontend `VITE_API_BASE_URL` to `https://api.yourdomain.com/api/v1`.  
7. Use Let’s Encrypt for HTTPS (free).

---

### 8.5 Minimal “all free” demo checklist

- [ ] Groq key in backend env (or set `INTENT_PROVIDER=rules` + `RAG_USE_LLM=false` + `INSIGHT_USE_LLM=false` for offline demo)  
- [ ] Backend live URL health: `GET /api/v1/health`  
- [ ] CORS allows Vercel origin  
- [ ] Frontend env points at backend  
- [ ] Persistent volume for `uploads` / `processed` / `rag` / `models`  
- [ ] Upload size limit acceptable for free host (`MAX_UPLOAD_SIZE_MB`)  
- [ ] Do **not** commit `.env` or API keys  

---

### 8.6 Cost-aware operating modes

| Mode | Settings | Use when |
|------|----------|----------|
| Full hybrid | `INTENT_PROVIDER=llm`, RAG/Insight LLM on | Best UX, uses Groq free quota |
| Offline / rules | `INTENT_PROVIDER=rules`, `RAG_USE_LLM=false`, `INSIGHT_USE_LLM=false` | No LLM spend; still analytics/viz/ML |
| Mixed | LLM intent + deterministic insight | Balance quality vs tokens |

---

## 9. What Phase 11 will add (not implemented yet)

Per constitution:

- Hardened production Docker / process management  
- Nginx + TLS wiring as first-class repo artifacts  
- Vercel project config and backend deploy scripts under `deployment/`  
- Production CORS, secrets management, and health monitoring notes  

---

## 10. Closing summary

InsightFlow AI was built as a **layered BI platform**:

1. **Data plane** — upload + profile  
2. **Control plane** — intent + memory + routing  
3. **Execution plane** — analytics, visualization, RAG, ML  
4. **Reasoning plane** — insight engine with evidence packs  
5. **Presentation plane** — React dashboard  

Each phase stayed backward-compatible, kept engines deterministic where possible, and reserved Groq for classification and narrative reasoning only.

---

*Report generated for InsightFlow AI Phases 0–10. Deployment section describes free-tier options suitable for demos; production hardening remains Phase 11.*
