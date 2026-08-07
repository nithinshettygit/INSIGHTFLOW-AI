# InsightFlow AI

Production-inspired AI Business Intelligence Platform.

InsightFlow AI is **not** a an LLM wrapper, or a chatbot over CSV. It is a modular platform that routes user questions through intent detection into specialized engines — analytics, visualization, ML, RAG — and uses an LLM only when reasoning or explanation is required.

## Architecture

```
User → Intent Detection → Appropriate Engine → LLM (only if needed) → Response
```

| Query type            | Engine                |
|-----------------------|-----------------------|
| Simple calculations   | Analytics Engine      |
| Charts                | Visualization Engine  |
| Forecast / ML         | ML Engine             |
| Document questions    | RAG Engine            |
| Explanation / advice  | Insight Engine (LLM)  |

The LLM receives processed summaries, never raw datasets when avoidable.

## Tech Stack

| Layer        | Technology                          |
|--------------|-------------------------------------|
| Frontend     | React, Vite, TailwindCSS, Axios     |
| Backend      | FastAPI                             |
| Orchestration| LangGraph                           |
| LLM          | Groq                                |
| Analytics    | Pandas                              |
| Visualization| Plotly                              |
| Vector Store | FAISS                               |
| Database     | SQLite                              |
| Backend host | AWS EC2 + Nginx                     |
| Frontend host| Vercel                              |

## Repository Layout

```
InsightFlow-AI/
├── PROJECT_CONSTITUTION.md   # Governing engineering rules
├── backend/                  # FastAPI app, engines, services
│   ├── app/
│   │   ├── api/              # HTTP routes
│   │   ├── core/             # Config, logging
│   │   ├── engines/          # Analytics, viz, ML, RAG, intent, insight
│   │   ├── services/         # Reusable business services
│   │   └── utils/            # Shared helpers
│   ├── data/                 # Uploads and processed artifacts
│   ├── models/               # Persisted ML artifacts
│   └── tests/
├── frontend/                 # React + Vite application
└── deployment/               # EC2, Nginx, release notes
```

## Development Phases

| Phase | Focus                                      | Status      |
|-------|--------------------------------------------|-------------|
| 0     | Project Foundation                         | Complete    |
| 1     | Backend Foundation (config, logging, API)  | Complete    |
| 2     | Dataset Upload (CSV, Excel, PDF)           | Complete    |
| 3     | Automatic Dataset Profiling                | Complete    |
| 4     | Intent Detection (LangGraph + Groq)        | Complete    |
| 5     | Analytics Engine                           | Complete    |
| 6     | Visualization Engine                       | Complete    |
| 7     | React Frontend                             | Complete    |
| 8     | RAG                                        | Complete    |
| 9     | Machine Learning                           | Complete    |
| 10    | Business Insight Engine                    | Complete    |
| 11    | Deployment                                 | Pending     |

## Getting Started

Phases 0–10 provide a runnable full stack: FastAPI engines (including Insight) + React dashboard.

```bash
# Clone
git clone <repo-url>
cd InsightFlow-AI
cp .env.example .env

# Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

- App: http://127.0.0.1:5173
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/v1/health
- RAG query: `POST /api/v1/rag/query`
- ML run: `POST /api/v1/ml/run`
- Insight: `POST /api/v1/insight/analyze`

See [PROJECT_CONSTITUTION.md](PROJECT_CONSTITUTION.md) for engineering rules, hybrid AI philosophy, and phase constraints.
See [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md) for details.

## Principles

1. Simplicity over complexity
2. Modular over monolithic
3. Deterministic processing over unnecessary AI
4. LLM as last option, not first
5. One responsibility per module
6. Configuration over hardcoding
7. Leave the project runnable after every change
