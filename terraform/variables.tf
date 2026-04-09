variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name used to prefix all resource names"
  type        = string
  default     = "medquery"
}

variable "environment" {
  description = "Deployment environment (e.g. prod, staging)"
  type        = string
  default     = "prod"
}

# --- Networking ---

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for the two public subnets (used by ALB)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for the two private subnets (used by ECS tasks)"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.20.0/24"]
}

# --- ECS ---

variable "backend_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 512
}

variable "backend_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 1024
}

variable "backend_desired_count" {
  description = "Number of ECS task replicas to run"
  type        = number
  default     = 1
}

# --- Secrets (values set via environment or CI/CD — never hard-coded here) ---

variable "openai_api_key" {
  description = "OpenAI API key — injected at plan/apply time via TF_VAR_openai_api_key"
  type        = string
  sensitive   = true
}

variable "tavily_api_key" {
  description = "Tavily API key for web search — injected at plan/apply time via TF_VAR_tavily_api_key"
  type        = string
  sensitive   = true
}

variable "app_api_key" {
  description = "Optional X-API-Key for the backend. Leave empty to disable auth."
  type        = string
  sensitive   = true
  default     = ""
}

# --- Database ---

variable "db_password" {
  description = "Master password for the RDS PostgreSQL instance — injected via TF_VAR_db_password"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

# --- Frontend ---

variable "frontend_domain" {
  description = "Custom domain for CloudFront (optional). Leave empty to use the auto-generated CloudFront URL."
  type        = string
  default     = ""
}
