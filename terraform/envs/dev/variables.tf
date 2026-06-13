# ── Core ──────────────────────────────────────────────────────────────────
variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "inditex-audit"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-west-2"
}

# ── Networking (shared VPC — no new VPC created) ──────────────────────────
variable "vpc_id" {
  description = "ID of the shared kn-playground-dev-vpc. Get from: cd applications/shared-infra/terraform/envs/dev && terraform output -raw shared_vpc_id"
  type        = string
}

variable "subnet_ids" {
  description = "Public subnet IDs in the shared VPC. Get from: cd applications/shared-infra/terraform/envs/dev && terraform output -json public_subnet_ids"
  type        = list(string)
}

# ── Backend — Elastic Beanstalk ───────────────────────────────────────────
variable "backend_instance_type" {
  description = "EC2 instance type for the Beanstalk environment"
  type        = string
  default     = "t3.small"
}

variable "backend_solution_stack" {
  description = "EB solution stack. Find latest: aws elasticbeanstalk list-available-solution-stacks | grep Docker"
  type        = string
  default     = "64bit Amazon Linux 2023 v4.13.1 running Docker"
}

# ── Database (shared RDS — same VPC, no peering needed) ───────────────────
variable "pg_host" {
  description = "Shared RDS endpoint. Get from: cd applications/shared-infra/terraform/envs/dev && terraform output -raw rds_endpoint"
  type        = string
}

variable "pg_port" {
  description = "PostgreSQL port"
  type        = number
  default     = 5432
}

variable "pg_user" {
  description = "PostgreSQL user (kn_admin master or a dedicated user)"
  type        = string
  default     = "kn_admin"
  sensitive   = true
}

variable "pg_password" {
  description = "PostgreSQL password. Get from: cd applications/shared-infra/terraform/envs/dev && terraform output -raw rds_master_password"
  type        = string
  sensitive   = true
}

variable "pg_database" {
  description = "Database name — the server auto-creates it on first startup"
  type        = string
  default     = "inditex_audit"
}

# ── Tags ──────────────────────────────────────────────────────────────────
variable "common_tags" {
  description = "Additional tags applied to all resources"
  type        = map(string)
  default = {
    Team = "KlearNow"
  }
}
