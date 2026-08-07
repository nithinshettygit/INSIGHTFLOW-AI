# InsightFlow AI — Final Project Report

**Product:** InsightFlow AI  
**Type:** Modular AI Business Intelligence Platform (not an LLM wrapper)  
**Version:** `0.10.0`  
**Phases covered:** 0–10 (Phase 11 deployment packaging pending)

This report explains **exactly how the running system works** — from opening the UI to upload, profile, intent routing, and every engine (analytics, visualization, RAG, ML, insight) — with the **project files involved at each step**.

---

## 1. What this project is

InsightFlow AI answers business questions by:

1. Understanding uploaded data (profile)  
2. Classifying the user’s question (intent)  
3. Sending work to a **specialized engine**  
4. Using an LLM **only** when reasoning/explanation is needed  

```
User question
    → Intent Detection (rules + LangGraph/Groq + memory)
        → Analytics | Visualization | RAG | ML | Insight | Profile | none
            → Results + optional chart in the React dashboard
```

| Question style | Engine | LLM? |
|----------------|--------|------|
| Totals / filters / lowest-highest | Analytics | No |
| Chart / plot / graph | Visualization | No |
| PDF / document says… | RAG | Optional |
| Forecast / segment / anomaly | ML | No |
| Why / recommend / explain | Insight | Yes (fallback offline) |
| Schema / missing values | Profiling | No |
| bye / thanks / gibberish | none | Short reply |

---

## 2. How to start the running system

### 2.1 Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # Windows
pip install -r requirements.txt
# Configure env (repo root): copy .env.example → .env ; set GROQ_API_KEY if using LLM
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Entrypoint:** `backend/app/main.py`  
- Creates FastAPI app (`create_app`)  
- On startup ensures folders: uploads, processed, models, rag  
- Mounts all routes under `/api/v1` via `backend/app/api/router.py`  
- CORS allows Vite (`http://127.0.0.1:5173`)  
- Docs: `http://127.0.0.1:8000/docs`

**Config:** `backend/app/core/config.py` + root `.env`  
**Logging:** `backend/app/core/logging.py`

### 2.2 Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **`http://127.0.0.1:5173`**

**Entrypoint:** `frontend/src/main.jsx` → `frontend/src/App.jsx`  
**API proxy:** `frontend/vite.config.js` forwards `/api` → `http://127.0.0.1:8000`  
**HTTP client:** `frontend/src/api/client.js` (`baseURL` = `/api/v1`)

---

## 3. Master runtime flow (start → finish)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. UI boots → health check → list datasets → create session_id │
│ 2. User uploads file → store + auto-profile (+ RAG index if PDF)│
│ 3. UI loads profile → ProfileCard in Results                     │
│ 4. User asks in chat → POST /intent/detect (+ session memory)    │
│ 5. App.jsx switches on target_engine                             │
│ 6. Engine runs → ResultsPanel / ChartPanel update                │
│ 7. Follow-ups reuse memory; bye/thanks clear topic               │
└─────────────────────────────────────────────────────────────────┘
```

The rest of this report expands each stage with files.

---

## 4. Stage A — Starting UI

### What the user sees
- Header: **InsightFlow AI**, selected dataset name, API status (`online` / `offline`)  
- **Datasets** hamburger (top-right) → drawer with upload/list/delete  
- Page 1: **Results** (left) + **Ask InsightFlow** chat (right)  
- Page 2 (scroll): **Visualization** chart area + “Back to Results”

### How it works in code

| Step | What happens | Files |
|------|----------------|-------|
| 1 | React mounts | `frontend/src/main.jsx`, `frontend/src/index.css`, Tailwind |
| 2 | `App` creates a **session id** (in-memory chat continuity) | `frontend/src/App.jsx` → `createSessionId()` |
| 3 | `GET /api/v1/health` | `client.healthCheck` → `backend/app/api/routes/health.py` |
| 4 | Status badge set to online/offline | `App.jsx` state `apiStatus` |
| 5 | `GET /api/v1/datasets` loads existing uploads | `client.listDatasets` → `datasets` route + `DatasetService` |
| 6 | Layout renders panels | `ResultsPanel`, `ChatPanel`, `ChartPanel`, `DatasetPanel` |

**Key UI files**

| File | Role |
|------|------|
| `frontend/src/App.jsx` | Orchestrator: state, upload, chat dispatch, engine routing |
| `frontend/src/components/ChatPanel.jsx` | Message list + query input |
| `frontend/src/components/ResultsPanel.jsx` | Profile / KPIs / tables / RAG / ML / insight / last intent |
| `frontend/src/components/ChartPanel.jsx` | Plotly figure |
| `frontend/src/components/DatasetPanel.jsx` | Upload, select, delete |
| `frontend/src/components/ProfileCard.jsx` | Friendly profile tiles + column table |
| `frontend/src/api/client.js` | All Axios calls |
| `frontend/src/lib/queryRouter.js` | Intent entities → engine payloads + extreme-answer text |

---

## 5. Stage B — Load dataset / file

### User action
Open **Datasets** → choose CSV / Excel / PDF → Upload.

### Frontend path
1. `DatasetPanel` calls `onUpload(file)`.  
2. `App.handleUpload` → `uploadDataset(file)` (`FormData`).  
3. On success: refresh list, select new `dataset_id`, open drawer briefly.

### Backend path

```
POST /api/v1/datasets/upload
  → backend/app/api/routes/datasets.py
  → DatasetService.upload()
```

**`DatasetService.upload` (`backend/app/services/dataset_service.py`) does:**

1. Validate type/size (`utils/files.py`, settings `MAX_UPLOAD_SIZE_MB`).  
2. Allocate `dataset_id` (UUID hex).  
3. Save file under `backend/data/uploads/{dataset_id}/`.  
4. Write `meta.json` (filename, type, size, timestamps).  
5. **Immediately profile** the file (Stage C).  
6. If PDF → **auto-index RAG** (Stage RAG).  
7. Return metadata to UI.

**Supporting files**

| File | Role |
|------|------|
| `backend/app/schemas/dataset.py` | Upload/list/meta models |
| `backend/app/utils/csv_io.py` | Encoding-safe CSV/Excel read |
| `backend/app/utils/files.py` | Safe paths / size checks |
| `backend/app/api/routes/datasets.py` | HTTP endpoints including delete |

**Delete:** UI confirm → `DELETE /api/v1/datasets/{id}` removes upload folder + related artifacts.

---

## 6. Stage C — Dataset profile (exact project behavior)

### When profiling runs
- **Automatically on every successful upload**  
- **Again whenever the UI selects a dataset** (`GET .../profile`)  
- Optionally refresh via `POST .../profile`

### Backend chain

```
DatasetService.upload / get_profile
  → ProfilingService.profile_dataset
  → persist profile.json + processed/{id}.profile.json
```

| File | Role |
|------|------|
| `backend/app/services/profiling_service.py` | Computes profile |
| `backend/app/schemas/profile.py` | Profile schema |
| `backend/data/uploads/{id}/profile.json` | Full profile next to file |
| `backend/data/processed/{id}.profile.json` | Compact summary for other engines |

### What profiling computes
**Tabular (CSV/Excel):**
- `row_count`, `column_count`  
- Per-column: name, dtype, nulls, unique count, stats / top values  
- Duplicate row count, missing total  
- Sample metadata / column name list  

**PDF:**
- Page count and document metadata (full text QA comes later via RAG)

### Frontend display

```
selectedId changes
  → getDatasetProfile(selectedId)
  → setProfile(data)
  → ResultsPanel → ProfileCard
```

| File | Role |
|------|------|
| `frontend/src/components/ProfileCard.jsx` | Stat tiles + column table (not raw JSON dump) |
| `frontend/src/components/ResultsPanel.jsx` | Shows profile when no analytics/RAG/ML/insight yet |

### Why profile matters later
Intent detection loads schema columns into LangGraph context so Groq/rules can only use **real column names**. Entity grounding (`entity_grounding.py`) also uses those names.

---

## 7. Stage D — User asks a question (chat)

### User action
Type in **Ask InsightFlow** → Send (requires a selected dataset for most engines).

### Frontend orchestration (`App.jsx`)

1. Append user message to `messages`.  
2. Call:

```js
detectIntent(text, selectedId, sessionId)
```

3. Read `intent.target_engine`.  
4. Branch:

| `target_engine` | Next call | Builder |
|-----------------|-----------|---------|
| `none` | Show `intent.reply` only | — |
| `visualization` | `createChart` | `buildVisualizationPayload` |
| `analytics` | `runAnalytics` | `buildAnalyticsPayload` |
| `rag` | `queryRag` | question + dataset_id |
| `ml` | `runMl` | `buildMlPayload` |
| `insight` | `analyzeInsight` | `buildInsightPayload` |
| `profiling` | `getDatasetProfile` | — |

5. Update `ResultsPanel` / `ChartPanel` / chat assistant text.  
6. For lowest/highest questions, `summarizeExtremeAnswer` turns the top row into:  
   `Canada has the lowest sales: 66,932.`

---

## 8. Stage E — Intent detection (control plane)

### API
`POST /api/v1/intent/detect`

```json
{ "query": "...", "dataset_id": "...", "session_id": "..." }
```

### Service
`backend/app/services/intent_service.py`  
→ builds detector from `INTENT_PROVIDER` (`llm` or `rules`)  
→ invokes LangGraph with `thread_id = session_id`

### Graph flow
`backend/app/engines/intent/graph.py`

```
load_context
  → load_memory
  → classify
  → apply_memory
  → ground_entities
  → route
  → save_memory
```

| Node | File(s) | What it does |
|------|---------|----------------|
| `load_context` | graph + `DatasetService.get_profile` | Attach dataset type, row counts, column schema |
| `load_memory` | `memory.py` | Load prior turns / last intent / last entities |
| `classify` | `llm_based.py` or `rule_based.py` | Choose intent + draft entities |
| `apply_memory` | `memory.py` | Follow-ups, closings, history; protect explicit viz |
| `ground_entities` | `entity_grounding.py` | Map names to real columns; keep measures out of dimensions |
| `route` | `rules.py` `ENGINE_ROUTING` | Ready/planned + short reply for unknown |
| `save_memory` | `memory.py` | Remember turn; clear topic on bye/thanks |

**Prompts:** `backend/app/engines/intent/prompts.py`  
**Rules/catalog:** `backend/app/engines/intent/rules.py`  
**Schemas:** `backend/app/schemas/intent.py`  
**Checkpoint:** LangGraph `MemorySaver` (process memory; not reload-persistent)

### Session memory behaviors
- `what about profit` → keep topic, swap metric  
- `what about Technology` after category chart → add filter  
- `which region has lowest sales` after a chart → analytics with correct dimension (not `sales` as dimension)  
- `dsd` / hello → short unknown reply  
- `bye` / `bai` / `fine` / `thanks` → closing reply + clear active topic  
- `what did I ask previously` → list recent questions  

---

## 9. Stage F — Analytics engine

### When
Intent → `analytics` (totals, by region, lowest/highest, filters, KPIs).

### Frontend
`buildAnalyticsPayload` → `POST /api/v1/analytics/query`

### Backend

```
analytics route
  → AnalyticsService
  → DatasetService.load_dataframe
  → AnalyticsEngine.execute
```

| File | Role |
|------|------|
| `backend/app/api/routes/analytics.py` | HTTP endpoint |
| `backend/app/services/analytics_service.py` | Glue |
| `backend/app/engines/analytics/engine.py` | Filter → aggregate → sort → limit → KPIs |
| `backend/app/schemas/analytics.py` | Request/response |
| `backend/app/utils/dataframe.py` | Coerce string `"408"` sales → numeric |

### Pipeline inside the engine
1. Resolve metric/dimension/filter columns (case-insensitive grounding).  
2. Apply filters.  
3. Compute KPIs (`sum` / `mean` / `min` / `max` / `count`).  
4. Group-by aggregate (`sales_sum`, `sales_mean`, …).  
5. Sort (e.g. ascending for “lowest”).  
6. Limit (often 1 for “which region…”).  
7. Return `results`, `kpis`, `applied`, row counts.

### UI outcome
- Chat: extreme answer or “Analytics complete — N result rows”  
- Results: KPI JSON + result table  
- Meta: `filtered after/before` (+ `memory` if memory applied)

---

## 10. Stage G — Visualization engine

### When
Intent → `visualization` (bar/line/pie/scatter).

### Frontend
`buildVisualizationPayload` → `POST /api/v1/visualization/chart`  
Title built from entities (e.g. `bar chart of sales by region (Category=Technology)`).

### Backend

```
visualization route
  → VisualizationService
  → VisualizationEngine (Plotly figure JSON)
```

| File | Role |
|------|------|
| `backend/app/api/routes/visualization.py` | Endpoint |
| `backend/app/services/visualization_service.py` | Glue |
| `backend/app/engines/visualization/engine.py` | Plotly builder |
| `backend/app/schemas/visualization.py` | Models |

### UI outcome
- `ChartPanel` renders `plotly_figure`  
- Chat: “Built a bar chart: …”  
- User scrolls to Visualization page  

Explicit chart asks are **not** overridden by prior analytics memory.

---

## 11. Stage H — RAG (PDF / document QA)

### When
- Upload a PDF → auto-index  
- Intent → `rag` (“what does the document say…”)

### Index-time (upload)

```
DatasetService._auto_index_pdf
  → RagService / RagEngine
  → chunk → embed → FAISS save under data/rag/
```

| File | Role |
|------|------|
| `backend/app/engines/rag/chunking.py` | Split text with overlap |
| `backend/app/engines/rag/embeddings.py` | Local hashed embeddings (no paid embed API) |
| `backend/app/engines/rag/store.py` | FAISS persistence |
| `backend/app/engines/rag/engine.py` | Index + retrieve + answer |
| `backend/app/engines/rag/prompts.py` | Optional Groq synthesis |
| `backend/app/services/rag_service.py` | App service |
| `backend/app/api/routes/rag.py` | `index` / `status` / `query` |
| `backend/app/schemas/rag.py` | Models |

### Query-time

```
App → queryRag({ dataset_id, question })
  → POST /api/v1/rag/query
  → retrieve top-k chunks → answer (+ sources)
```

### UI outcome
Answer in chat; sources listed in Results.

---

## 12. Stage I — Machine Learning engine

### When
Intent → `ml` (forecast, segmentation/clustering, anomaly/outlier).

### Frontend
`buildMlPayload` infers task from wording if needed → `POST /api/v1/ml/run`

### Backend

```
ml route → MlService → MLEngine
  → forecast.py | segmentation.py | anomaly.py
```

| File | Role |
|------|------|
| `backend/app/api/routes/ml.py` | Endpoint |
| `backend/app/services/ml_service.py` | Glue |
| `backend/app/engines/ml/engine.py` | Task router |
| `backend/app/engines/ml/forecast.py` | Trend / seasonal-naive style forecast |
| `backend/app/engines/ml/segmentation.py` | KMeans clusters |
| `backend/app/engines/ml/anomaly.py` | IsolationForest outliers |
| `backend/app/engines/ml/helpers.py` | Column/feature helpers |
| `backend/app/schemas/ml.py` | Models |
| `backend/models/` | Optional persisted artifacts |

### UI outcome
- Summary in Results  
- If `plotly_figure` returned → shown in ChartPanel  

---

## 13. Stage J — Business Insight engine

### When
Intent → `insight` (why / explain / recommend / root cause).

### Design rule
LLM never gets the raw CSV. It gets a **compact evidence pack**.

### Backend

```
insight route
  → InsightService
  → InsightEngine
      → evidence.py (pack KPIs / segments / optional ML context)
      → Groq prompts OR deterministic.py fallback
```

| File | Role |
|------|------|
| `backend/app/api/routes/insight.py` | Endpoint |
| `backend/app/services/insight_service.py` | Glue |
| `backend/app/engines/insight/engine.py` | Orchestrator |
| `backend/app/engines/insight/evidence.py` | Evidence pack builder |
| `backend/app/engines/insight/prompts.py` | LLM prompts |
| `backend/app/engines/insight/deterministic.py` | Offline narrative |
| `backend/app/schemas/insight.py` | Models |

### Modes
- `explanation`  
- `recommendation`  
- `root_cause`  

### UI outcome
Headline + explanation in chat; findings / recommendations / root causes in Results.

---

## 14. Stage K — Conversation finish / unknown

| User says | Behavior | Files |
|-----------|----------|-------|
| `bye`, `bai`, `thanks`, `fine`, `ok`, `done` | Short closing; clear active topic | `memory.py` `looks_like_conversation_end` |
| `hello`, `dsd` | Short help reply; no engine | route `none` + `ENGINE_ROUTING` reply |
| `what did I ask previously` | Lists recent questions | `build_history_reply` |

Frontend: `engine === "none"` shows `intent.reply` only.

---

## 15. End-to-end example (tabular demo)

**Dataset:** `SuperStore_Orders.csv`

| # | User | System path | Typical result |
|---|------|-------------|----------------|
| 1 | Upload CSV | upload → profile → ProfileCard | rows/cols/stats |
| 2 | “bar chart of sales by region” | intent=visualization → Plotly | 13 regions chart |
| 3 | “which region has lowest sales” | intent=analytics (+ memory) → sort asc | e.g. Canada + sum |
| 4 | “what about profit” | memory follow-up → analytics metric=profit | profit by same grain |
| 5 | “forecast next month sales” | intent=ml → forecast | forecast series/chart |
| 6 | “why is profit low in Canada?” | intent=insight → evidence + LLM | explanation |
| 7 | “bye” | none + close memory | goodbye text |

**PDF demo:** upload PDF → auto FAISS index → “According to the document…” → RAG answer with sources.

---

## 16. Layered architecture (how files fit together)

```
frontend/src/App.jsx          Presentation + orchestration
        ↓ HTTP
backend/app/api/routes/*      Controllers
        ↓
backend/app/services/*        Use-cases (load data, call engines)
        ↓
backend/app/engines/*         Domain algorithms (deterministic first)
        ↓
backend/app/schemas/*         Contracts
backend/app/core/*            Config + logging
backend/data|models           Runtime artifacts
```

**Router aggregation:** `backend/app/api/router.py` includes health, datasets, intent, analytics, visualization, rag, ml, insight.

---

## 17. Configuration that changes runtime behavior

Root `.env` (from `.env.example`):

| Variable | Effect |
|----------|--------|
| `GROQ_API_KEY` | Enables LLM intent / RAG synthesis / insight |
| `INTENT_PROVIDER=llm\|rules` | Groq graph vs offline keywords |
| `RAG_USE_LLM` | RAG answer with/without Groq |
| `INSIGHT_USE_LLM` | Insight with/without Groq |
| `UPLOAD_DIR` / `PROCESSED_DIR` / `RAG_DIR` / `MODEL_DIR` | Artifact locations |
| `MAX_UPLOAD_SIZE_MB` | Upload cap |

Offline-friendly: rules intent + `RAG_USE_LLM=false` + `INSIGHT_USE_LLM=false` still runs analytics, viz, ML, deterministic insight.

---

## 18. API checklist (full running surface)

| Method | Path | Stage |
|--------|------|-------|
| GET | `/api/v1/health` | UI boot |
| POST | `/api/v1/datasets/upload` | Load file |
| GET | `/api/v1/datasets` | List |
| GET/DELETE | `/api/v1/datasets/{id}` | Select/delete |
| GET/POST | `/api/v1/datasets/{id}/profile` | Profile |
| POST | `/api/v1/intent/detect` | Intent + memory |
| GET | `/api/v1/intent/catalog` | Supported intents |
| POST | `/api/v1/analytics/query` | Analytics |
| POST | `/api/v1/visualization/chart` | Charts |
| POST | `/api/v1/rag/index` | Index PDF |
| GET | `/api/v1/rag/{id}/status` | Index status |
| POST | `/api/v1/rag/query` | Document QA |
| POST | `/api/v1/ml/run` | Forecast / segment / anomaly |
| POST | `/api/v1/insight/analyze` | Explain / recommend / root cause |

Interactive docs while backend runs: `http://127.0.0.1:8000/docs`

---

## 19. Testing the running system

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

| Tests | Cover |
|-------|--------|
| `test_health.py`, `test_config.py` | Boot/config |
| `test_datasets.py` | Upload |
| `test_profiling.py` | Profile |
| `test_intent.py` | Intent + memory |
| `test_analytics.py` | Analytics |
| `test_visualization.py` | Charts |
| `test_rag.py` | RAG |
| `test_ml.py` | ML |
| `test_insight.py` | Insight |

---

## 20. Deployment snapshot (free tier)

Full write-up also lives in `PHASES_0_10_IMPLEMENTATION_REPORT.md` §8.

| Piece | Free option |
|-------|-------------|
| Frontend | Vercel Hobby (`npm run build` → `dist`) |
| Backend | Render / Railway / Fly.io free allowance |
| LLM | Groq free API tier |
| Vectors/ML | Local FAISS + sklearn (no paid vector DB) |

Set `VITE_API_BASE_URL` to the public backend `/api/v1`, open CORS to the Vercel origin, and attach a persistent disk for uploads/profiles/rag/models.

---

## 21. Final summary

InsightFlow AI runs as a **closed loop**:

1. **Start UI** → health + datasets + session  
2. **Upload** → disk registry + **automatic profile** (+ RAG index for PDFs)  
3. **Show profile** in Results via ProfileCard  
4. **Ask** → **intent graph** with schema + memory  
5. **Route** to Analytics / Visualization / RAG / ML / Insight / Profile / none  
6. **Render** answers, tables, and Plotly charts  
7. **Continue or close** the conversation cleanly  

That is the complete starting-to-finishing flow of this project as implemented in the current codebase.

---

*Companion docs:* `PROJECT_CONSTITUTION.md` (rules & roadmap) · `PHASES_0_10_IMPLEMENTATION_REPORT.md` (phase build history & file lists) · this `PROJECT_REPORT.md` (runtime flow).
