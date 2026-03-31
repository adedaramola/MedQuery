# MedQuery

A **medical question-answering system** built with FastAPI, LangGraph, and PostgreSQL + pgvector. Queries are routed across a medical Q&A corpus, FDA drug label data, and live web search, with a relevance check loop before generating a streamed answer.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ React Frontend (src/)                                   │
│ - Streaming chat UI (token-by-token via SSE)            │
│ - Source quality badge, routing info                    │
│ - Conversation history per session                      │
│ - Medical scope guardrail (non-medical queries blocked) │
└──────────────────┬──────────────────────────────────────┘
                   │ SSE + REST
┌──────────────────▼──────────────────────────────────────┐
│ FastAPI Backend (backend/)                              │
│ ┌─────────────────────────────────────────────┐        │
│ │ LangGraph Pipeline                          │        │
│ │  START → Router → [QnA|Device|Web] →       │        │
│ │          Relevance Check → Augment →       │        │
│ │          Generate → END                     │        │
│ └─────────────────────────────────────────────┘        │
│ - Safety guardrail: scope check + harm patterns        │
│ - OpenAI GPT-4o-mini (routing, generation, scope)      │
│ - OpenAI Embeddings (similarity search)                │
│ - DuckDuckGo Search (web fallback, no API key needed)  │
│ - Streaming SSE responses                              │
│ - PostgreSQL conversation history + pgvector search    │
└──────────────────┬──────────────────────────────────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
┌────▼──────┐ ┌───▼──────┐ ┌───▼───────┐
│PostgreSQL │ │OpenAI    │ │DuckDuckGo │
│+ pgvector │ │API       │ │(free)     │
│(QnA+FDA)  │ │(LLM)     │ │           │
└───────────┘ └──────────┘ └───────────┘
```

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Docker (recommended) or PostgreSQL 16 with pgvector extension
- OpenAI API key

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env: set OPENAI_API_KEY and POSTGRES_PASSWORD

docker-compose up
```

The stack starts three containers: `db` (pgvector), `backend` (FastAPI), `frontend` (nginx). Alembic migrations run automatically on backend startup.

Open `http://localhost:3000`.

### Option B — Local

```bash
# Install dependencies
npm install   # also creates .venv and installs Python packages

# Configure environment
cp .env.example .env
# Set OPENAI_API_KEY and DATABASE_URL in .env

# Run migrations
source .venv/bin/activate
alembic upgrade head

# Start backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Start frontend (new terminal)
npm start
```

### Ingest Data

```bash
curl -X POST "http://localhost:8000/api/ingest"
```

Data sources (in `data/`):
- `medical_pubmed.csv` — PubMed abstracts (run `data/fetch_real_data.py` to refresh)
- `medical_fda_labels.csv` — FDA drug label excerpts

## API Endpoints

### `POST /api/query/stream`
Streaming RAG endpoint (SSE).

**Request:**
```json
{
  "query": "What are contraindications for a pacemaker?",
  "conversation_id": "session-uuid"
}
```

**SSE Events:**
```
data: {"type": "meta", "source": "Medical Q&A Collection", "source_info": {...}, "relevance": {...}}

data: {"type": "token", "token": "Contra"}
data: {"type": "token", "token": "indications"}
...

data: {"type": "done", "answer": "...", "source_quality": {"tier": "verified_corpus", ...}, "timestamp": "..."}
```

### `POST /api/query`
Non-streaming endpoint.

**Response:**
```json
{
  "query": "What are contraindications for a pacemaker?",
  "answer": "Contraindications include active infections...",
  "source": "Medical Q&A Collection",
  "source_quality": {"tier": "verified_corpus", "label": "Verified corpus (structured medical data)"},
  "source_info": {"routing": "medical_knowledge", "reason": "..."},
  "relevance": {"is_relevant": true, "reason": "..."},
  "iteration_count": 1,
  "timestamp": "2025-03-06T10:30:45.123456"
}
```

### `GET /api/health`
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "models": {"llm": "gpt-4o-mini", "embeddings": "text-embedding-3-small"},
  "databases": {"qa_collection_count": 298, "device_collection_count": 500}
}
```

### `POST /api/ingest`
Ingest CSV data into PostgreSQL/pgvector. Safe to call multiple times (upsert).

## Pipeline

1. **Safety check** — GPT-4o-mini classifies whether the query is medical/health-related; non-medical queries are rejected before retrieval. High-risk harm patterns are blocked separately.
2. **Router** — decides retrieval source: Q&A corpus, device/drug data, or web search
3. **Retriever** — fetches top-N documents via cosine similarity (pgvector) or DuckDuckGo
4. **Relevance check** — validates whether the context answers the question; falls back to web search if not (max 3 iterations)
5. **Augment** — builds a RAG prompt with context + conversation history
6. **Generate** — streams the answer token-by-token via SSE

## Configuration

Key settings in `backend/config.py` (all overridable via environment variables):

```python
LLM_MODEL      = "gpt-4o-mini"
EMBED_MODEL    = "text-embedding-3-small"
N_RESULTS      = 5    # documents retrieved per query
MAX_ITERATIONS = 3    # max relevance-check loops
MAX_HISTORY_TURNS = 10
```

## Deployment

### AWS (Terraform)

Infrastructure is defined in [`terraform/`](terraform/) and provisions:
- **ECS Fargate** — backend container (migrations run on startup)
- **ECR** — Docker image registry
- **ALB** — public load balancer
- **RDS PostgreSQL 16** — vector store + conversation history (private subnet)
- **S3 + CloudFront** — React frontend (HTTPS, `/api/*` proxied to ALB)
- **Secrets Manager** — `OPENAI_API_KEY`, `DATABASE_URL`
- **IAM user** — least-privilege CI/CD credentials for GitHub Actions

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Fill in: openai_api_key, db_password

terraform init
terraform apply
```

After apply, copy the CI credentials into GitHub:
```bash
terraform output github_actions_secrets
```

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs tests, builds Docker images, and deploys to ECS on every push to `main`.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `OPENAI_API_KEY not set` | Copy `.env.example` → `.env`, fill in your key |
| Backend won't start | Run `npm install` (re-runs postinstall), check Python 3.10+ |
| `DATABASE_URL not set` | Add `DATABASE_URL=postgresql://...` to `.env` |
| PostgreSQL connection error | Check DB is running: `pg_isready`; verify `DATABASE_URL` |
| pgvector extension missing | Run `CREATE EXTENSION vector;` in your database |
| Port already in use | `lsof -ti :8000 \| xargs kill -9` |
| Frontend can't reach API | Ensure backend runs on port 8000 |
| "Backend disconnected" on CloudFront | Rebuild frontend with `REACT_APP_API_URL` pointing to CloudFront (not ALB directly) |

## Documentation

- [QUICKSTART.md](docs/QUICKSTART.md)
- [SETUP.md](docs/SETUP.md)
- [ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Interactive API docs: `http://localhost:8000/docs`
