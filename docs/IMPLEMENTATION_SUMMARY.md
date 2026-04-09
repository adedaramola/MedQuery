# MedQuery – Implementation Summary

## What Was Built

A **production-grade Agentic RAG system** for medical knowledge retrieval, with LangGraph-based dynamic routing, safety guardrails, streaming responses, real medical data ingestion, full Docker containerisation, and AWS deployment via Terraform.

---

## File Reference

### Backend (`backend/`)

| File | Purpose |
|------|---------|
| `config.py` | Constants, env vars (`TAVILY_API_KEY`, `MAX_TOKENS_PER_TURN`, `MAX_HISTORY_TURNS`), JSON log formatter |
| `models.py` | Pydantic schemas (`QueryResponse` with `source_quality`; `SourceQualityInfo`) + `GraphState` TypedDict |
| `auth.py` | `require_api_key` FastAPI dependency — checks `X-API-Key` header |
| `limiter.py` | Shared `slowapi` rate-limiter (20 req/min per IP) |
| `llm.py` | LLM provider abstraction — `get_llm_response()` and `stream_llm_response()` work across OpenAI, Anthropic, and any OpenAI-compatible endpoint; `LLM_BASE_URL` empty string treated as unset to avoid Docker connection errors |
| `safety.py` | Safety guardrails: `check_safety()` classifies queries as `BLOCKED` / `FLAGGED` / `SAFE`; `append_safety_disclaimer()` appends medical disclaimers to flagged responses |
| `db.py` | psycopg2 `ThreadedConnectionPool`; `get_conn()` (plain) and `get_vector_conn()` (pgvector adapter registered) |
| `history.py` | PostgreSQL conversation store with turn-count and token-aware truncation (`_truncate_to_token_budget()`) |
| `vector_store.py` | pgvector tables with HNSW indexes; `ingest_data()` prioritises real CSVs (PubMed, FDA) over synthetic fallbacks |
| `pipeline/state.py` | `compute_source_quality()` — returns tier/label/disclaimer dict; replaces the old heuristic confidence float |
| `pipeline/nodes.py` | All LangGraph nodes; `web_search` uses Tavily (requires `TAVILY_API_KEY`); `get_llm_response` imported from `backend/llm.py` |
| `pipeline/graph.py` | `build_agentic_rag()` graph builder; `query_rag()` executor; `stream_rag_response()` SSE generator using `stream_llm_response()` |
| `routes/query.py` | Safety gate before all queries; `POST /api/query`; `POST /api/query/stream` (auth + rate limited) |
| `routes/health.py` | `GET /api/health`, `POST /api/ingest`, `GET /` |
| `main.py` | FastAPI app init, CORS middleware, rate limiter mount, request-ID middleware |

### Frontend (`src/`)

| File | Purpose |
|------|---------|
| `App.jsx` | Full chat UI: SSE stream consumption, message state, source quality badge, streaming cursor |
| `constants.js` | `API_BASE` — reads `REACT_APP_API_URL` (baked in at build time); defaults to `http://localhost:8000` for local dev |
| `components/MessageBubble.jsx` | Renders individual messages with source tier badge and safety disclaimer display |
| `components/Header.jsx` | App header with backend health status indicator |
| `components/TypingIndicator.jsx` | Animated typing indicator during streaming |

### Data (`data/`)

| File | Purpose |
|------|---------|
| `fetch_real_data.py` | Downloads real medical data from PubMed E-utilities (786 abstracts) and openFDA drug labels (23 labels); outputs `medical_pubmed.csv` and `medical_fda_labels.csv`; each abstract block has a unique Question key to prevent deduplication collisions |
| `generate_data.py` | Generates synthetic fallback datasets using `CONDITIONS × QNA_TEMPLATES` combinations |
| `medical_pubmed.csv` | 786 real PubMed abstracts across 20 clinical topics — primary Q&A corpus |
| `medical_fda_labels.csv` | 23 real FDA drug labels — primary device/drug corpus |
| `medical_q_n_a.csv` | Synthetic Q&A dataset — not ingested unless real data is absent |
| `medical_device_manuals_dataset.csv` | Synthetic device dataset — not ingested unless real data is absent |

### Migrations (`migrations/`)

| File | Purpose |
|------|---------|
| `env.py` | Alembic environment — reads `DATABASE_URL` from environment |
| `script.py.mako` | Template for new migration files |
| `versions/20240101_0001_initial_schema.py` | Creates `medical_qna`, `medical_device`, `conversation_turns` tables and HNSW indexes; includes `downgrade()` |

### Scripts (`scripts/`)

| File | Purpose |
|------|---------|
| `smoke_test.py` | Interactive CLI for manual backend testing (health check, queries, ingest) — development use only |
| `docker-entrypoint.sh` | Container startup script: runs `alembic upgrade head` then starts `uvicorn`; used as `ENTRYPOINT` in `Dockerfile` |

### Infrastructure

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies (pinned): LangGraph 0.3.5, LangChain 0.3.13, `openai>=1.58.1`, `tavily-python`, `alembic` |
| `package.json` | Node.js deps |
| `.env.example` | Fully documented secrets template: `OPENAI_API_KEY`, `DATABASE_URL`, `POSTGRES_PASSWORD`, `TAVILY_API_KEY`, `ALLOWED_ORIGINS`, `API_KEY`, `MAX_HISTORY_TURNS`, `NCBI_API_KEY` |
| `.dockerignore` | Excludes `.env`, `node_modules`, `.venv`, `tests/`, `terraform/`, `docs/` from Docker build context |
| `Dockerfile` | Backend container: copies `backend/`, `data/`, `migrations/`, `alembic.ini`, `scripts/docker-entrypoint.sh`; ENTRYPOINT runs migrations then uvicorn |
| `Dockerfile.frontend` | Multi-stage frontend build: Node 18 Alpine (build) → nginx 1.25 Alpine (serve); `REACT_APP_API_URL` baked in as build arg |
| `nginx.conf` | nginx: SPA fallback routing, `/api/*` proxy to `backend:8000`, SSE buffering disabled, `/nginx-health` health check endpoint |
| `docker-compose.yml` | Full-stack local orchestration: `db` (pgvector/pgvector:pg16) + `backend` (depends on db healthy) + `frontend` (depends on backend healthy); `DATABASE_URL` injected with Docker-internal hostname |
| `alembic.ini` | Alembic configuration |
| `.github/workflows/ci.yml` | CI/CD: test (pgvector container), build, docker, ECS deploy |

### Terraform (`terraform/`)

| File | Purpose |
|------|---------|
| `main.tf` | AWS provider, Terraform version constraint, optional S3 remote state |
| `variables.tf` | All inputs: region, CPU/memory, secrets, DB class, frontend domain |
| `outputs.tf` | `backend_url`, `frontend_url`, `ecr_repository_url`, `s3_frontend_bucket`, `rds_endpoint`, `github_actions_secrets` (sensitive — prints all CI secret values) |
| `vpc.tf` | VPC, public/private subnets across 2 AZs, IGW, NAT Gateway, security groups |
| `iam.tf` | ECS execution role (ECR + CloudWatch + Secrets Manager) + task role + `medquery-github-ci` IAM user (ECR push, ECS update, S3 sync, CloudFront invalidation) |
| `secrets.tf` | Secrets Manager secrets: `OPENAI_API_KEY`, `API_KEY`, `DATABASE_URL` |
| `ecr.tf` | ECR repository + lifecycle policy (retains 2 most recent images) |
| `rds.tf` | RDS PostgreSQL 16 in private subnets; custom parameter group; pgvector-compatible |
| `alb.tf` | Application Load Balancer, target group, HTTP listener, CloudWatch log group |
| `ecs.tf` | Fargate cluster + task definition (secrets injected from Secrets Manager) + rolling-update service |
| `s3_cloudfront.tf` | Private S3 bucket + CloudFront distribution with OAC (no public bucket access) |

---

## Agentic Pipeline

```
safety_check (backend/safety.py)
    ├── BLOCKED  → crisis response (pipeline never runs)
    └── SAFE / FLAGGED →
          ↓
        Router → [retrieve_clinical | retrieve_device | web_search]
                           ↓
                  check_relevance
                    ├── relevant   → augment → generate → END
                    └── irrelevant → web_search → check_relevance (max 3 loops)
```

- **router** and **check_relevance** both use `temperature=0` for deterministic decisions
- **web_search** uses Tavily API (requires `TAVILY_API_KEY`; raises an error if unset)
- The loop cap (`MAX_ITERATIONS=3`) prevents runaway retries
- All LLM calls routed through `backend/llm.py` — no direct SDK imports in pipeline nodes

---

## Key Design Decisions

**Safety before pipeline**
`check_safety()` runs synchronously before any DB or LLM call. BLOCKED queries never reach the pipeline — cost is zero and there is no risk of an unsafe answer being generated.

**Source quality, not confidence**
The old `compute_confidence()` heuristic (90% for Q&A, 85% for devices, etc.) was replaced with `compute_source_quality()`, which returns a structured descriptor with `tier`, `label`, `is_relevant`, `iterations`, and a mandatory `disclaimer`. The UI shows the tier rather than a percentage.

**Real data only by default**
The ingest command passes empty strings for the synthetic CSV paths so only `medical_pubmed.csv` (786 records) and `medical_fda_labels.csv` (23 records) are loaded. Synthetic fallbacks are available but not ingested unless explicitly passed.

**Unique PubMed question keys**
Each PubMed abstract block gets a unique `Question` field (`[PubMed] {query} [{n}]`) so `drop_duplicates` in `ingest_data()` doesn't collapse all abstracts for the same topic into one row.

**LLM provider abstraction**
`backend/llm.py` is the only place that imports an LLM SDK. Changing `LLM_PROVIDER` in `.env` switches the entire system to a different provider without touching any pipeline or route code. `LLM_BASE_URL` empty string is treated as `None` (`os.getenv("LLM_BASE_URL") or None`) — passing an empty string directly to the OpenAI client caused `UnsupportedProtocol` errors inside Docker.

**Database containerised with pgvector**
`docker-compose.yml` includes a `db` service (`pgvector/pgvector:pg16`) with a named volume (`pgdata`) for persistence. `DATABASE_URL` is overridden inside Docker to point to the `db` container hostname. `POSTGRES_PASSWORD` in `.env` is used by both the db container and the backend connection string.

**Automatic migrations on startup**
`scripts/docker-entrypoint.sh` runs `alembic upgrade head` before starting uvicorn. Alembic's migration tracking makes this idempotent — already-applied migrations are skipped.

**pgvector connection split**
`get_conn()` returns a plain connection for schema DDL. `get_vector_conn()` calls `register_vector(conn)` for vector operations. This ensures the pgvector adapter is registered only after `CREATE EXTENSION vector` has run.

**Stable upsert IDs**
Vector store IDs are MD5 hashes of `"{source_label}:{question}"`. Re-ingesting the same data is safe — rows are updated in place via `ON CONFLICT (id) DO UPDATE`. The source label prefix prevents ID collisions between real and synthetic rows.

**Token-aware history**
History is bounded by both turn count (`MAX_HISTORY_TURNS`) and an estimated token budget (`MAX_HISTORY_TURNS × MAX_TOKENS_PER_TURN`). The oldest turns are dropped first, preserving the most recent context even for verbose conversations.

**Production frontend container**
`Dockerfile.frontend` uses a two-stage build: Node 18 Alpine compiles the React bundle, then nginx 1.25 Alpine serves it. `REACT_APP_API_URL` is baked in as `http://localhost` so the browser hits nginx on port 80, which proxies `/api/*` to the backend internally. `nginx.conf` disables proxy buffering for `/api/*` so SSE tokens stream immediately.

**Alembic for schema management**
Schema changes go through Alembic migrations instead of ad-hoc `CREATE TABLE IF NOT EXISTS` calls. The initial migration (`0001`) creates all three tables and can be rolled back with `alembic downgrade -1`.

---

## Configuration

All constants in `backend/config.py` — override with environment variables:

```python
LLM_MODEL           = "gpt-4o-mini"
EMBED_MODEL         = "text-embedding-3-small"
DATABASE_URL        = "postgresql://localhost/medical_rag"
N_RESULTS           = 5
MAX_ITERATIONS      = 3
MAX_HISTORY_TURNS   = 10       # also configurable via MAX_HISTORY_TURNS env var
MAX_TOKENS_PER_TURN = 300      # chars-to-token ratio ≈ 4:1
ALLOWED_ORIGINS     = "http://localhost:3000"
API_KEY             = ""
TAVILY_API_KEY      = ""       # required for web search
```

---

## Common Customisations

| Goal | Where to change |
|------|----------------|
| Switch LLM provider | `LLM_PROVIDER` in `.env` + install provider SDK |
| Switch LLM model | `LLM_MODEL` in `backend/config.py` |
| Add a safety pattern | `_BLOCKED_PATTERNS` or `_FLAGGED_PATTERNS` in `backend/safety.py` |
| Retrieve more documents | `N_RESULTS` in `backend/config.py` |
| Change routing logic | `router_node()` in `backend/pipeline/nodes.py` |
| Change answer prompt | `augment()` in `backend/pipeline/nodes.py` |
| Add a new SSE event type | `stream_rag_response()` in `backend/pipeline/graph.py` |
| Add a new data source | New table in `vector_store.py` + new node in `nodes.py` + new edge in `graph.py` |
| Add a migration | `alembic revision -m "description"` then edit the generated file |
| Change DB password | `POSTGRES_PASSWORD` in `.env` (rebuild containers after changing) |

---

## Documentation Index

| File | Contents |
|------|---------|
| [QUICKSTART.md](QUICKSTART.md) | 5-minute local setup and Docker quick start |
| [SETUP.md](SETUP.md) | Full setup, Docker, AWS deployment, CI/CD |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design, data flow, LangGraph workflow, Docker architecture, safety layer |
| http://localhost:8000/docs | Interactive API documentation (Swagger UI) |
