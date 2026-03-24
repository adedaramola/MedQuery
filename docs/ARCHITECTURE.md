# Architecture

## Project Structure

```
medicalAgenticRag/
│
├── backend/                        # Python backend (FastAPI)
│   ├── config.py                   # Constants, env vars, JSON log formatter
│   ├── models.py                   # Pydantic schemas + GraphState TypedDict
│   ├── auth.py                     # API key dependency (X-API-Key header)
│   ├── limiter.py                  # Shared slowapi rate-limiter instance
│   ├── llm.py                      # LLM provider abstraction (OpenAI / Anthropic / Ollama)
│   ├── safety.py                   # Safety guardrails: BLOCKED / FLAGGED query classification
│   ├── db.py                       # psycopg2 ThreadedConnectionPool (get_conn / get_vector_conn)
│   ├── history.py                  # PostgreSQL conversation store (token-aware truncation)
│   ├── vector_store.py             # pgvector tables, HNSW indexes, query/ingest (real + synthetic)
│   ├── pipeline/
│   │   ├── state.py                # compute_source_quality() descriptor
│   │   ├── nodes.py                # All LangGraph node functions (Tavily/DDG web search)
│   │   └── graph.py                # build_agentic_rag(), query_rag(), stream_rag_response()
│   ├── routes/
│   │   ├── query.py                # POST /api/query, POST /api/query/stream (safety gate)
│   │   └── health.py               # GET /api/health, POST /api/ingest, GET /
│   └── main.py                     # FastAPI app, CORS, rate limiter, request ID middleware
│
├── src/                            # React frontend
│   ├── App.jsx                     # Main chat UI (SSE streaming, source badges, history)
│   ├── index.js                    # React entry point
│   ├── constants.js                # Shared constants
│   └── components/
│       ├── Header.jsx
│       ├── MessageBubble.jsx       # Renders message with source_quality badge
│       └── TypingIndicator.jsx
│
├── data/                           # Datasets and ingestion scripts
│   ├── generate_data.py            # Synthetic CSV generator (fallback only)
│   ├── fetch_real_data.py          # Fetches real data from PubMed + openFDA APIs
│   ├── medical_q_n_a.csv           # Synthetic Q&A dataset (fallback)
│   └── medical_device_manuals_dataset.csv  # Synthetic device dataset (fallback)
│
├── migrations/                     # Alembic database migrations
│   ├── env.py                      # Alembic environment (reads DATABASE_URL)
│   ├── script.py.mako              # Migration template
│   └── versions/
│       └── 20240101_0001_initial_schema.py  # Initial tables + indexes
│
├── scripts/                        # Utility scripts (not part of the app)
│   └── smoke_test.py               # Manual CLI smoke tester (was test_system.py)
│
├── tests/                          # Automated test suite
│   ├── conftest.py                 # Pytest fixtures, make_state(), mock DB helpers
│   ├── test_api.py                 # Integration tests for all API endpoints
│   ├── test_confidence.py          # Unit tests for compute_source_quality()
│   ├── test_history.py             # Unit tests for conversation history + token truncation
│   └── test_nodes.py               # Unit tests for every LangGraph node
│
├── terraform/                      # AWS infrastructure (Terraform)
│   ├── main.tf, variables.tf, outputs.tf
│   ├── vpc.tf, iam.tf, secrets.tf
│   ├── ecr.tf, rds.tf, alb.tf, ecs.tf
│   └── s3_cloudfront.tf
│
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions: test → build → docker → deploy
│
├── docs/                           # Documentation
├── public/index.html               # React HTML shell
├── requirements.txt                # Python dependencies (pinned)
├── package.json                    # Node.js dependencies
├── Dockerfile                      # Backend container (uvicorn, linux/amd64)
├── Dockerfile.frontend             # Frontend container (multi-stage: Node build → nginx)
├── nginx.conf                      # nginx: SPA routing + /api/* proxy + SSE support
├── docker-compose.yml              # Local full-stack orchestration
├── alembic.ini                     # Alembic configuration
└── .env.example                    # Documented secrets template
```

## What Makes This Agentic

Standard RAG always retrieves from the same source and generates. This system is agentic because:

1. **Dynamic routing** — an LLM decides at runtime which source to query (Q&A database, device manual database, or live web search) based on the nature of the question.

2. **Relevance checking loop** — after retrieval, a second LLM call evaluates whether the retrieved context actually answers the question. If not, it re-routes to web search and tries again.

3. **Conditional branching** — the LangGraph graph has real conditional edges that change execution path based on LLM decisions, not fixed rules.

4. **Fallback tool use** — Tavily search is used as a tool when local knowledge is insufficient, giving the system access to current information without a pre-indexed corpus.

## Safety Layer

All queries pass through `backend/safety.py` **before** entering the LangGraph pipeline:

| Risk Level | Trigger | Behaviour |
|------------|---------|-----------|
| `BLOCKED` | Overdose intent, suicide method, harm-to-others patterns | Returns crisis helpline response immediately — pipeline never runs |
| `FLAGGED` | Drug interactions, max dosing, abrupt discontinuation | Answer is generated normally, then a safety disclaimer is appended |
| `SAFE` | Everything else | Passes through unmodified |

## LangGraph Workflow

```
START
  ↓
safety_check  (backend/safety.py — before graph)
  ├── BLOCKED  → return crisis response immediately
  └── SAFE / FLAGGED →
        ↓
      router  (LLM at temperature=0 — deterministic)
        ├── "medical_knowledge" → retrieve_clinical
        ├── "device_manual"     → retrieve_device
        └── "web_search"        → web_search (Tavily or DuckDuckGo fallback)
                ↓
          check_relevance  (LLM at temperature=0)
            ├── relevant     → augment → generate → END
            └── not relevant → web_search → check_relevance (loop, max 3 iterations)
```

Key design decisions:
- Router and relevance checker both run at `temperature=0` for deterministic, consistent routing
- The relevance loop has a hard cap of `MAX_ITERATIONS=3` to prevent infinite loops
- Web search is both a primary route and a fallback, keeping the graph simple

## LLM Provider Abstraction

All LLM calls go through `backend/llm.py`, not directly to the OpenAI SDK. This allows swapping providers without touching pipeline code:

| `LLM_PROVIDER` | Required env var | Notes |
|---------------|-----------------|-------|
| `openai` (default) | `OPENAI_API_KEY` | Also works with `LLM_BASE_URL` for Azure, Ollama, vLLM |
| `anthropic` | `ANTHROPIC_API_KEY` | Uses `anthropic` SDK |

## Data Flow

```
User types query
    ↓
src/App.jsx  (sendMessage)
    └── POST /api/query/stream  (SSE connection)
    ↓
backend/routes/query.py
    ├── Safety gate (check_safety) — BLOCKED queries short-circuit here
    ├── Load conversation history from PostgreSQL (token-aware truncation)
    └── stream_rag_response(query, history)
    ↓
backend/pipeline/graph.py
    ├── Run full LangGraph pipeline in thread pool
    ├── Emit SSE "meta" event  (source, routing reason, relevance)
    ├── Emit SSE "token" events  (streamed from LLM)
    └── Emit SSE "done" event  (full answer, source_quality, timestamp)
    ↓
Browser renders streaming tokens with blinking cursor
    └── Finalises with source badge, source quality tier, iteration count
```

## Data Sources

The ingest pipeline supports both real and synthetic data. **Real data takes priority.**

| CSV | Source | Priority |
|-----|--------|---------|
| `data/medical_pubmed.csv` | PubMed E-utilities API (free) | 1st — real clinical abstracts |
| `data/medical_q_n_a.csv` | Synthetic generator | Fallback only |
| `data/medical_fda_labels.csv` | openFDA drug labels API (free) | 1st — real drug label text |
| `data/medical_device_manuals_dataset.csv` | Synthetic generator | Fallback only |

Run `python data/fetch_real_data.py` to download real data. Synthetic rows are tagged with `SYNTHETIC — do not rely on for clinical decisions` in the `source_label` metadata field.

## Database Design

All persistence is in **PostgreSQL + pgvector**. Three tables:

| Table | Purpose | Key Columns |
|-------|---------|------------|
| `medical_qna` | Q&A vector store | `id TEXT`, `content TEXT`, `embedding vector(1536)`, `metadata JSONB` |
| `medical_device` | Device manual vector store | `id TEXT`, `content TEXT`, `embedding vector(1536)`, `metadata JSONB` |
| `conversation_turns` | Chat history | `conversation_id TEXT`, `role TEXT`, `content TEXT`, `created_at TIMESTAMPTZ` |

Both vector tables use **HNSW indexes** (`vector_cosine_ops`) for fast approximate nearest-neighbour search. IDs are MD5 hashes of the source text, enabling safe upserts.

Schema is managed by **Alembic** migrations (`migrations/`). Run `alembic upgrade head` before starting the server for the first time, or after any schema change.

## Source Quality

Replaced the old heuristic "confidence score" with an honest `source_quality` descriptor in `backend/pipeline/state.py`. This is **not** a confidence score — it describes retrieval origin only.

| Source | Tier | Label |
|--------|------|-------|
| Medical Q&A Collection, Medical Device Manual | `verified_corpus` | Verified corpus (structured medical data) |
| Web Search (Tavily / DuckDuckGo) | `external_web` | External web search (unverified) |
| Web Search (failed) | `failed` | Retrieval failed |
| Unknown | `unknown` | Unknown source |

Every response also carries a `disclaimer` field: *"Source quality reflects the retrieval origin, not answer correctness. Always verify medical information with a qualified healthcare professional."*

## Conversation History — Token-Aware Truncation

`backend/history.py` applies two bounds before returning history to the pipeline:

1. **Turn count**: at most `MAX_HISTORY_TURNS` (default 10) user+assistant turn pairs
2. **Token budget**: estimated token count (4 chars ≈ 1 token) capped at `MAX_HISTORY_TURNS × MAX_TOKENS_PER_TURN`; oldest turns are dropped first

This prevents long prior turns from blowing the context window even when the turn count is within the limit.

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | None | Service info |
| GET | `/api/health` | None | System health + record counts |
| POST | `/api/ingest` | None | Load CSVs from `data/` into pgvector |
| POST | `/api/query` | Optional `X-API-Key` | Non-streaming query |
| POST | `/api/query/stream` | Optional `X-API-Key` | Streaming query (SSE) |

Rate limit: 20 requests/min per IP.

## AWS Infrastructure

```
Internet
    │
    ├── CloudFront (HTTPS) → S3 (React build, private bucket + OAC)
    │
    └── ALB (HTTP) → ECS Fargate (FastAPI)
                         │
                         ├── RDS PostgreSQL 16 (private subnet, pgvector)
                         └── Secrets Manager (OPENAI_API_KEY, DATABASE_URL, API_KEY, TAVILY_API_KEY)
```

All ECS tasks run in private subnets. RDS is not publicly accessible. Secrets are injected as environment variables at task startup via Secrets Manager — never stored in the image or task definition plaintext.

## CI/CD Pipeline

`.github/workflows/ci.yml` runs on every push to `main` and every PR:

| Stage | Trigger | Action |
|-------|---------|--------|
| `backend-test` | All pushes/PRs | pytest against real pgvector container |
| `frontend-build` | All pushes/PRs | `npm ci && npm run build` |
| `docker-build` | After tests pass | Build both Docker images (cache to GHA) |
| `deploy` | Push to `main` only | Push to ECR, force ECS redeployment |

## Key Configuration

All constants in `backend/config.py`:

```python
LLM_MODEL           = "gpt-4o-mini"
EMBED_MODEL         = "text-embedding-3-small"
DATABASE_URL        = "postgresql://localhost/medical_rag"  # override via .env
N_RESULTS           = 5        # documents retrieved per query
MAX_ITERATIONS      = 3        # max relevance-check loop iterations
MAX_HISTORY_TURNS   = 10       # conversation turns kept per session
MAX_TOKENS_PER_TURN = 300      # token budget per history turn
ALLOWED_ORIGINS     = "http://localhost:3000"
API_KEY             = ""       # enables X-API-Key auth when non-empty
TAVILY_API_KEY      = ""       # production web search (DuckDuckGo used if empty)
```
