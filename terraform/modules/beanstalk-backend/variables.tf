variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, production)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where the EB environment will be created"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for the EB environment (public subnets)"
  type        = list(string)
}

variable "instance_type" {
  description = "EC2 instance type for the Beanstalk environment"
  type        = string
  default     = "t3.small"
}

variable "solution_stack_name" {
  description = "Elastic Beanstalk solution stack. Find latest: aws elasticbeanstalk list-available-solution-stacks | grep Docker"
  type        = string
  default     = "64bit Amazon Linux 2023 v4.13.1 running Docker"
}

# ── PostgreSQL (shared RDS) ───────────────────────────────────────────────
variable "pg_host" {
  description = "Shared RDS endpoint hostname"
  type        = string
}

variable "pg_port" {
  description = "PostgreSQL port"
  type        = number
  default     = 5432
}

variable "pg_user" {
  description = "PostgreSQL user (kn_admin or a dedicated user)"
  type        = string
  sensitive   = true
}

variable "pg_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "pg_database" {
  description = "Database name — server auto-creates it on first startup"
  type        = string
  default     = "inditex_audit"
}

# ── Tags ──────────────────────────────────────────────────────────────────
variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
