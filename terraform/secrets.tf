# ──────────────────────────────────────────────────────────
# Secrets Manager
# Values are passed in via TF_VAR_* environment variables at
# plan/apply time — they are never written to .tf files or
# state in plain text (state is encrypted in S3).
# ──────────────────────────────────────────────────────────

resource "aws_secretsmanager_secret" "openai_api_key" {
  name                    = "${var.app_name}/${var.environment}/openai-api-key"
  description             = "OpenAI API key for the Medical RAG backend"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = var.openai_api_key
}

resource "aws_secretsmanager_secret" "db_url" {
  name                    = "${var.app_name}/${var.environment}/database-url"
  description             = "PostgreSQL DATABASE_URL for the Medical RAG backend"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id     = aws_secretsmanager_secret.db_url.id
  secret_string = "postgresql://medical_rag_user:${var.db_password}@${aws_db_instance.postgres.endpoint}/medical_rag"
}

resource "aws_secretsmanager_secret" "tavily_api_key" {
  name                    = "${var.app_name}/${var.environment}/tavily-api-key"
  description             = "Tavily API key for web search"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "tavily_api_key" {
  secret_id     = aws_secretsmanager_secret.tavily_api_key.id
  secret_string = var.tavily_api_key
}

resource "aws_secretsmanager_secret" "app_api_key" {
  count                   = var.app_api_key != "" ? 1 : 0
  name                    = "${var.app_name}/${var.environment}/app-api-key"
  description             = "Optional X-API-Key for the Medical RAG backend. Leave empty to disable."
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app_api_key" {
  count         = var.app_api_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.app_api_key[0].id
  secret_string = var.app_api_key
}
