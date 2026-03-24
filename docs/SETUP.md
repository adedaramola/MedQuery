# Medical Agentic RAG – Setup & Deployment Guide

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| PostgreSQL | 16 | with pgvector extension |
| Docker | 24+ | required for Docker Compose and AWS deployment |
| Terraform | 1.6+ | required for AWS deployment |
| AWS CLI | 2.x | required for AWS deployment |

---

## Local Development

### 1. Install PostgreSQL 16

**macOS:**
```bash
brew install postgresql@16
brew services start postgresql@16
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

**Ubuntu/Debian:**
```bash
sudo apt install -y postgresql-16 postgresql-16-pgvector
sudo systemctl start postgresql
```

### 2. Create the Database and Enable pgvector

```bash
createdb medical_rag
psql medical_rag -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 3. Clone and Install Dependencies

```bash
git clone https://github.com/adedaramola/medicalAgenticRag.git
cd medicalAgenticRag

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Node packages (frontend only — no postinstall Python hook)
npm ci --ignore-scripts
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```
# Required
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql://<your-system-username>@localhost/medical_rag

# Recommended
TAVILY_API_KEY=tvly-...      # production web search; DuckDuckGo used if absent
API_KEY=your-secret          # enables X-API-Key header auth; leave empty to disable
ALLOWED_ORIGINS=http://localhost:3000

# Optional
MAX_HISTORY_TURNS=10
API_HOST=0.0.0.0
API_PORT=8000
API_LOG_LEVEL=info
# NCBI_API_KEY=...           # raises PubMed rate limit from 3 to 10 req/s
```

On macOS, `<your-system-username>` is the output of `whoami`. A local PostgreSQL install does not require a password.

### 5. Run Database Migrations

```bash
alembic upgrade head
```

Creates `medical_qna`, `medical_device`, and `conversation_turns` tables with HNSW indexes.

To roll back:
```bash
alembic downgrade -1
```

### 6. Fetch Real Medical Data (Recommended)

```bash
python data/fetch_real_data.py
```

Downloads:
- **PubMed abstracts** via NCBI E-utilities (free, no auth) → `data/medical_pubmed.csv`
- **FDA drug labels** via openFDA API (free, no auth) → `data/medical_fda_labels.csv`

If you skip this step, the system falls back to synthetic datasets. Synthetic rows are tagged as such in ingested metadata.

Optional flags:
```bash
python data/fetch_real_data.py --pubmed-queries 10 --pubmed-per-query 5 --fda-drugs 15
```

### 7. Start the Backend

```bash
source .venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 8. Ingest Data

```bash
curl -X POST http://localhost:8000/api/ingest
```

The ingest endpoint automatically picks up all available CSVs in `data/`. Real data takes priority over synthetic fallbacks.

### 9. Start the Frontend

```bash
npm start
```

Frontend opens at http://localhost:3000.

---

## Run Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

All 85 tests are offline — no live database or API key needed. External calls (OpenAI, pgvector, Tavily, DuckDuckGo) are fully mocked.

---

## Docker Compose

For a containerised local environment:

```bash
cp .env.example .env   # fill in OPENAI_API_KEY and DATABASE_URL
docker compose up --build
```

The frontend (`Dockerfile.frontend`) builds a static nginx bundle — no `npm install` at runtime.

After services are healthy (the backend health check runs every 30s):
```bash
curl -X POST http://localhost:8000/api/ingest
```

Access:
- Frontend: http://localhost:80
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

---

## Production Deployment — AWS (Terraform)

### Architecture

```
Browser → CloudFront (HTTPS) → S3 (React static bundle)
Browser → ALB → ECS Fargate (FastAPI backend)
ECS Fargate → RDS PostgreSQL 16 (pgvector + conversation history)
ECS Fargate → Secrets Manager (OPENAI_API_KEY, DATABASE_URL, API_KEY)
```

### Step 1: Provision Infrastructure

```bash
cd terraform

export TF_VAR_openai_api_key="sk-..."
export TF_VAR_db_password="your-strong-db-password"
export TF_VAR_app_api_key=""   # leave empty to disable API key auth

terraform init
terraform plan
terraform apply
```

Note the outputs:
```bash
terraform output
# backend_url         = "http://<alb-dns>"
# frontend_url        = "https://<cloudfront-id>.cloudfront.net"
# ecr_repository_url  = "<account>.dkr.ecr.us-east-1.amazonaws.com/medical-rag"
# s3_frontend_bucket  = "medical-rag-frontend-<suffix>"
```

### Step 2: Build and Push the Backend Image

> Apple Silicon (M1/M2/M3) users must build for `linux/amd64` — ECS Fargate runs x86_64.

```bash
ECR_URL=$(terraform output -raw ecr_repository_url)

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin $ECR_URL

docker build --platform linux/amd64 -t "${ECR_URL}:latest" .
docker push "${ECR_URL}:latest"
```

Force a new ECS deployment:
```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
SERVICE=$(terraform output -raw ecs_service_name)
aws ecs update-service --cluster $CLUSTER --service $SERVICE --force-new-deployment
```

### Step 3: Run Database Migrations on RDS

Connect to the RDS instance (via a bastion or ECS exec) and run:
```bash
DATABASE_URL="postgresql://..." alembic upgrade head
```

Or use AWS Systems Manager Session Manager to reach the ECS task.

### Step 4: Build and Deploy the Frontend

```bash
cd ..   # back to project root
BACKEND_URL=$(cd terraform && terraform output -raw backend_url)
echo "REACT_APP_API_URL=${BACKEND_URL}" > .env.production
npm run build
```

Sync to S3 and invalidate CloudFront:
```bash
S3_BUCKET=$(cd terraform && terraform output -raw s3_frontend_bucket)
aws s3 sync build/ s3://$S3_BUCKET --delete

DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='medical-rag frontend'].Id | [0]" \
  --output text)
aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

### Step 5: Ingest Data

Once the ECS task is healthy (check the ALB target group):
```bash
BACKEND=$(cd terraform && terraform output -raw backend_url)
curl -X POST ${BACKEND}/api/ingest
```

### Step 6: Verify

```bash
BACKEND=$(cd terraform && terraform output -raw backend_url)
curl ${BACKEND}/api/health | python3 -m json.tool
```

The frontend is accessible at the `frontend_url` Terraform output.

---

## CI/CD (GitHub Actions)

The pipeline in `.github/workflows/ci.yml` runs automatically:

| Event | Stages run |
|-------|-----------|
| Push to any branch / PR to `main` | `backend-test` → `frontend-build` → `docker-build` |
| Push to `main` | All above + `deploy` (pushes to ECR, redeploys ECS) |

Required GitHub repository secrets for the `deploy` stage:

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | IAM key with ECR push + ECS update permissions |
| `AWS_SECRET_ACCESS_KEY` | Corresponding secret |
| `AWS_REGION` | e.g. `us-east-1` |
| `ECR_REGISTRY` | e.g. `123456789.dkr.ecr.us-east-1.amazonaws.com` |
| `ECR_BACKEND_REPO` | ECR repo name for the backend image |
| `ECR_FRONTEND_REPO` | ECR repo name for the frontend image |
| `ECS_CLUSTER` | ECS cluster name |
| `ECS_SERVICE_BACKEND` | ECS service name for the backend |
| `CLOUDFRONT_DOMAIN` | CloudFront domain for `REACT_APP_API_URL` bake-in |

---

## Updating a Deployed Stack

**Backend code change:**
```bash
ECR_URL=$(cd terraform && terraform output -raw ecr_repository_url)
docker build --platform linux/amd64 -t "${ECR_URL}:latest" .
docker push "${ECR_URL}:latest"
aws ecs update-service \
  --cluster $(cd terraform && terraform output -raw ecs_cluster_name) \
  --service $(cd terraform && terraform output -raw ecs_service_name) \
  --force-new-deployment
```

**Frontend change:**
```bash
npm run build
aws s3 sync build/ s3://$(cd terraform && terraform output -raw s3_frontend_bucket) --delete
DIST_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='medical-rag frontend'].Id | [0]" --output text)
aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/*"
```

**Schema change:**
```bash
# Generate a new migration
alembic revision -m "add new column"

# Edit the generated file in migrations/versions/, then apply
alembic upgrade head
```

---

## Configuration Reference

All constants are in `backend/config.py`. Override any with environment variables:

```python
LLM_MODEL           = "gpt-4o-mini"          # LLM_MODEL env var
EMBED_MODEL         = "text-embedding-3-small"
DATABASE_URL        = "postgresql://localhost/medical_rag"
N_RESULTS           = 5                       # documents retrieved per query
MAX_ITERATIONS      = 3                       # max relevance-check loop iterations
MAX_HISTORY_TURNS   = 10                      # MAX_HISTORY_TURNS env var
MAX_TOKENS_PER_TURN = 300                     # token budget per history turn
ALLOWED_ORIGINS     = "http://localhost:3000" # ALLOWED_ORIGINS env var (comma-separated)
API_KEY             = ""                      # enables X-API-Key auth when non-empty
TAVILY_API_KEY      = ""                      # set to use Tavily; unset = DuckDuckGo fallback
```

To switch LLM provider:
```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Supported providers: `openai` (default), `anthropic`. Any OpenAI-compatible endpoint can be used by setting `LLM_BASE_URL`.

---

## Security Checklist

- Store all secrets in `.env` — never commit this file
- `OPENAI_API_KEY` and `DATABASE_URL` are stored in AWS Secrets Manager
- Set `API_KEY` to require `X-API-Key` header on all query endpoints in production
- Set `ALLOWED_ORIGINS` to your CloudFront domain in production
- Rate limiting: 20 requests/min per IP (via `slowapi`)
- Safety guardrails block overdose/self-harm queries before any LLM call
- RDS runs in private subnets — not publicly accessible
- Enable HTTPS on the ALB by adding an ACM certificate to `terraform/alb.tf`

---

## Development Workflow

```bash
# Create a feature branch
git checkout -b feature/your-feature

# Run tests before committing
source .venv/bin/activate
pytest tests/ -v

# Commit (CI will run automatically on push)
git add backend/ src/ tests/
git commit -m "feat: your feature description"
git push origin feature/your-feature
```

---

## Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
- [Tavily API](https://tavily.com)
- [openFDA API](https://open.fda.gov/apis/)
- [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25500/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
