# ──────────────────────────────────────────────────────────
# Bootstrap — Remote State Infrastructure
#
# Run this ONCE before using the main terraform config.
# It creates the S3 bucket and DynamoDB table that the main
# config uses as its backend.
#
# Steps:
#   1. cd terraform/bootstrap
#   2. terraform init
#   3. terraform apply
#   4. Copy the bucket name from the output into
#      terraform/main.tf backend "s3" { bucket = "..." }
#   5. Uncomment the backend block in terraform/main.tf
#   6. cd .. && terraform init   (migrates local state to S3)
# ──────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
  # Intentionally no backend block — state is stored locally
  # in terraform/bootstrap/terraform.tfstate
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name — must match the value in terraform/variables.tf"
  type        = string
  default     = "medquery"
}

# ──────────────────────────────────────────────────────────
# Random suffix — keeps the bucket name globally unique
# without exposing account ID
# ──────────────────────────────────────────────────────────
resource "random_id" "state_bucket_suffix" {
  byte_length = 4
}

# ──────────────────────────────────────────────────────────
# S3 Bucket — stores terraform.tfstate for the main config
# ──────────────────────────────────────────────────────────
resource "aws_s3_bucket" "terraform_state" {
  bucket = "${var.app_name}-tfstate-${random_id.state_bucket_suffix.hex}"

  # Prevent accidental deletion of state
  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name      = "${var.app_name}-terraform-state"
    ManagedBy = "terraform-bootstrap"
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ──────────────────────────────────────────────────────────
# DynamoDB Table — state locking (prevents concurrent applies)
# ──────────────────────────────────────────────────────────
resource "aws_dynamodb_table" "terraform_lock" {
  name         = "${var.app_name}-tfstate-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Name      = "${var.app_name}-terraform-lock"
    ManagedBy = "terraform-bootstrap"
  }
}

# ──────────────────────────────────────────────────────────
# Outputs — copy these into terraform/main.tf backend block
# ──────────────────────────────────────────────────────────
output "state_bucket_name" {
  description = "Paste this into the bucket field of the backend block in terraform/main.tf"
  value       = aws_s3_bucket.terraform_state.bucket
}

output "dynamodb_lock_table" {
  description = "Paste this into the dynamodb_table field of the backend block in terraform/main.tf"
  value       = aws_dynamodb_table.terraform_lock.name
}

output "next_steps" {
  value = <<-EOT
    ✅ Bootstrap complete. Now do the following:

    1. Open terraform/main.tf
    2. Uncomment the backend "s3" block
    3. Set:
         bucket         = "${aws_s3_bucket.terraform_state.bucket}"
         dynamodb_table = "${aws_dynamodb_table.terraform_lock.name}"
         region         = "${var.aws_region}"
    4. Run: cd .. && terraform init
       (Terraform will ask to copy local state to S3 — answer yes)
  EOT
}
