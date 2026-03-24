# Quick Start

## TL;DR

```bash
# 1. Install deps & configure
cp .env.example .env   # fill in OPENAI_API_KEY and DATABASE_URL
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm ci --ignore-scripts

# 2. Run database migrations
alembic upgrade head

# 3. Fetch real data (optional but recommended)
python data/fetch_real_data.py

# 4. Terminal 1: Backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# 5. Terminal 2: Frontend
npm start

# 6. Ingest data
curl -X POST http://localhost:8000/api/ingest

# Open http://localhost:3000
```

---

## Step-by-Step

### 1. Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 16 with pgvector

Install PostgreSQL 16 (macOS):
```bash
brew install postgresql@16
brew services start postgresql@16
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Install PostgreSQL 16 (Ubuntu/Debian):
```bash
sudo apt install -y postgresql-16 postgresql-16-pgvector
sudo systemctl start postgresql
```

### 2. Create the Database

```bash
createdb medical_rag
psql medical_rag -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 3. Install Dependencies

```bash
git clone https://github.com/adedaramola/medicalAgenticRag.git
cd medicalAgenticRag

# Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Node
npm ci --ignore-scripts
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` — the minimum required fields:
```
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://<your-system-username>@localhost/medical_rag
```

Optional but recommended:
```
TAVILY_API_KEY=tvly-...      # production web search (DuckDuckGo used if not set)
API_KEY=your-secret          # enables X-API-Key auth on query endpoints
ALLOWED_ORIGINS=http://localhost:3000
MAX_HISTORY_TURNS=10
```

> On macOS, `<your-system-username>` is the output of `whoami`. No password needed for a local PostgreSQL install.

### 5. Run Database Migrations

```bash
alembic upgrade head
```

This creates the `medical_qna`, `medical_device`, and `conversation_turns` tables with HNSW indexes.

> If you are upgrading from a previous version that created tables on startup, Alembic's `CREATE TABLE IF NOT EXISTS` statements are safe to re-run.

### 6. Fetch Real Data (Recommended)

```bash
python data/fetch_real_data.py
```

Downloads real medical abstracts from PubMed and drug labels from openFDA. Both APIs are free with no authentication required. Rate limits are respected automatically.

If you skip this step, the system falls back to the synthetic datasets in `data/`.

### 7. Start the Backend

```bash
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
{"level": "INFO", "message": "PostgreSQL schema ready"}
```

### 8. Ingest Data

```bash
curl -X POST http://localhost:8000/api/ingest
```

Expected response:
```json
{"status": "success", "qa_records": 520, "device_records": 275}
```

Record counts vary depending on whether real data was fetched.

### 9. Start the Frontend

```bash
npm start
```

Browser opens at http://localhost:3000.

---

## Run Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

All 85 tests run offline — no live database or OpenAI API key required.

---

## Verify Setup

```bash
curl http://localhost:8000/api/health | python3 -m json.tool
```

Expected:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "models": { "llm": "gpt-4o-mini", "embeddings": "text-embedding-3-small" },
  "databases": { "qa_collection_count": 520, "device_collection_count": 275 }
}
```

---

## Test Queries

| Query | Expected Route | Safety |
|-------|---------------|--------|
| "What are symptoms of diabetes?" | Medical Q&A | Safe |
| "Contraindications for a pacemaker?" | Device Manual | Safe |
| "Latest COVID-19 antiviral medications?" | Web Search | Safe |
| "What are the side effects of metformin?" | Medical Q&A | Flagged — disclaimer appended |
| "How do I overdose on paracetamol?" | — | Blocked — crisis response returned |

---

## Docker (Alternative)

```bash
docker compose up --build
```

This builds the backend image and a production nginx frontend image, then starts both services. The frontend is served on port 80.

After services are healthy:
```bash
curl -X POST http://localhost:8000/api/ingest
```

---

## What You Get

- **Backend API** at http://localhost:8000
- **Frontend UI** at http://localhost:3000 (or http://localhost:80 via Docker)
- **API Documentation** at http://localhost:8000/docs
- Streaming responses (token-by-token via SSE)
- Source quality tier and routing badge on every response
- Safety guardrails — dangerous queries blocked, sensitive topics flagged
- Persistent conversation history per session (token-aware truncation)

---

## Documentation

- **Full Setup & Deployment**: [SETUP.md](SETUP.md)
- **Architecture & Data Flow**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Implementation Details**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
