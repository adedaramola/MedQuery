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

  backend "s3" {
    bucket  = "allthingspractice"
    key     = "medquery/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.app_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Fetch the current AWS account ID and region for use in ARNs
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Availability zones in the chosen region
data "aws_availability_zones" "available" {
  state = "available"
}
