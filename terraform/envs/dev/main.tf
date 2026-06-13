terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — create S3 bucket first (see BACKEND_SETUP.md):
  #   aws s3api create-bucket --bucket inditex-audit-terraform-state \
  #     --region us-west-2 --create-bucket-configuration LocationConstraint=us-west-2
  #   aws s3api put-bucket-versioning --bucket inditex-audit-terraform-state \
  #     --versioning-configuration Status=Enabled
  #   aws s3api put-bucket-encryption --bucket inditex-audit-terraform-state \
  #     --server-side-encryption-configuration \
  #     '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  backend "s3" {
    bucket       = "inditex-audit-terraform-state"
    key          = "inditex-audit/dev/terraform.tfstate"
    region       = "us-west-2"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# ── Backend — Flask app on Elastic Beanstalk ──────────────────────────────
# Deployed directly in the shared kn-playground-dev-vpc.
# No separate VPC or peering needed — RDS is in the same VPC.
module "beanstalk_backend" {
  source = "../../modules/beanstalk-backend"

  project_name        = var.project_name
  environment         = var.environment
  aws_region          = var.aws_region
  vpc_id              = var.vpc_id
  subnet_ids          = var.subnet_ids
  instance_type       = var.backend_instance_type
  solution_stack_name = var.backend_solution_stack

  pg_host     = var.pg_host
  pg_port     = var.pg_port
  pg_user     = var.pg_user
  pg_password = var.pg_password
  pg_database = var.pg_database

  tags = var.common_tags
}
