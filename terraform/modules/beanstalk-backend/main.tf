# ============================================================
# Beanstalk Backend Module — Inditex Audit
# Python 3.11 Flask app on a single t3.small EC2 instance.
# Connects to the shared kn-playground PostgreSQL RDS via
# VPC peering. No local RDS — database_url comes from shared.
# ============================================================

data "aws_caller_identity" "current" {}

# ── S3: Elastic Beanstalk App Versions ────────────────────────────────────
resource "aws_s3_bucket" "app_versions" {
  bucket = "${var.project_name}-${var.environment}-backend-versions-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-backend-versions"
  })
}

resource "aws_s3_bucket_versioning" "app_versions" {
  bucket = aws_s3_bucket.app_versions.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "app_versions" {
  bucket = aws_s3_bucket.app_versions.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "app_versions" {
  bucket                  = aws_s3_bucket.app_versions.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── IAM: Elastic Beanstalk Service Role ───────────────────────────────────
resource "aws_iam_role" "eb_service_role" {
  name = "${var.project_name}-${var.environment}-eb-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "elasticbeanstalk.amazonaws.com"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = "elasticbeanstalk"
          }
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "eb_service_enhanced_health" {
  role       = aws_iam_role.eb_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSElasticBeanstalkEnhancedHealth"
}

resource "aws_iam_role_policy_attachment" "eb_service_managed_updates" {
  role       = aws_iam_role.eb_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkManagedUpdatesCustomerRolePolicy"
}

# ── IAM: EC2 Instance Role ────────────────────────────────────────────────
resource "aws_iam_role" "eb_instance_role" {
  name = "${var.project_name}-${var.environment}-eb-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "eb_web_tier" {
  role       = aws_iam_role.eb_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkWebTier"
}

resource "aws_iam_role_policy_attachment" "ssm_managed" {
  role       = aws_iam_role.eb_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch_logs" {
  role       = aws_iam_role.eb_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

resource "aws_iam_role_policy" "s3_app_versions_access" {
  name = "${var.project_name}-${var.environment}-s3-app-versions"
  role = aws_iam_role.eb_instance_role.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AppVersionsS3Access"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.app_versions.arn,
          "${aws_s3_bucket.app_versions.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "eb_instance_profile" {
  name = "${var.project_name}-${var.environment}-eb-instance-profile"
  role = aws_iam_role.eb_instance_role.name
}

# ── Security Group ────────────────────────────────────────────────────────
resource "aws_security_group" "backend" {
  name        = "${var.project_name}-${var.environment}-backend-sg"
  description = "Inditex Audit Elastic Beanstalk"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-backend-sg"
  })
}

# ── Elastic Beanstalk Application ─────────────────────────────────────────
resource "aws_elastic_beanstalk_application" "backend" {
  name        = "${var.project_name}-${var.environment}-backend"
  description = "Inditex 7501 Audit — Flask API + Dashboard"

  appversion_lifecycle {
    service_role          = aws_iam_role.eb_service_role.arn
    max_count             = 5
    delete_source_from_s3 = true
  }

  tags = var.tags
}

# ── Elastic Beanstalk Environment ─────────────────────────────────────────
resource "aws_elastic_beanstalk_environment" "backend" {
  name                = "${var.project_name}-${var.environment}-env"
  application         = aws_elastic_beanstalk_application.backend.name
  solution_stack_name = var.solution_stack_name
  tier                = "WebServer"

  # ── VPC / Networking ────────────────────────────────────────────────────
  setting {
    namespace = "aws:ec2:vpc"
    name      = "VPCId"
    value     = var.vpc_id
  }

  setting {
    namespace = "aws:ec2:vpc"
    name      = "Subnets"
    value     = join(",", var.subnet_ids)
  }

  setting {
    namespace = "aws:ec2:vpc"
    name      = "AssociatePublicIpAddress"
    value     = "true"
  }

  # ── Environment Type: Single Instance ────────────────────────────────────
  setting {
    namespace = "aws:elasticbeanstalk:environment"
    name      = "EnvironmentType"
    value     = "SingleInstance"
  }

  setting {
    namespace = "aws:elasticbeanstalk:environment"
    name      = "ServiceRole"
    value     = aws_iam_role.eb_service_role.arn
  }

  # ── EC2 / Instance ────────────────────────────────────────────────────────
  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "InstanceType"
    value     = var.instance_type
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "IamInstanceProfile"
    value     = aws_iam_instance_profile.eb_instance_profile.name
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "SecurityGroups"
    value     = aws_security_group.backend.id
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "RootVolumeType"
    value     = "gp3"
  }

  setting {
    namespace = "aws:autoscaling:launchconfiguration"
    name      = "RootVolumeSize"
    value     = "20"
  }

  # ── Auto Scaling (locked to 1 for single instance) ───────────────────────
  setting {
    namespace = "aws:autoscaling:asg"
    name      = "MinSize"
    value     = "1"
  }

  setting {
    namespace = "aws:autoscaling:asg"
    name      = "MaxSize"
    value     = "1"
  }

  # ── Health Reporting ──────────────────────────────────────────────────────
  setting {
    namespace = "aws:elasticbeanstalk:healthreporting:system"
    name      = "SystemType"
    value     = "enhanced"
  }

  # ── Managed Platform Updates ──────────────────────────────────────────────
  setting {
    namespace = "aws:elasticbeanstalk:managedactions"
    name      = "ManagedActionsEnabled"
    value     = "true"
  }

  setting {
    namespace = "aws:elasticbeanstalk:managedactions"
    name      = "PreferredStartTime"
    value     = "Sun:03:00"
  }

  setting {
    namespace = "aws:elasticbeanstalk:managedactions:platformupdate"
    name      = "UpdateLevel"
    value     = "minor"
  }

  # ── CloudWatch Log Streaming ──────────────────────────────────────────────
  setting {
    namespace = "aws:elasticbeanstalk:cloudwatch:logs"
    name      = "StreamLogs"
    value     = "true"
  }

  setting {
    namespace = "aws:elasticbeanstalk:cloudwatch:logs"
    name      = "DeleteOnTerminate"
    value     = "false"
  }

  setting {
    namespace = "aws:elasticbeanstalk:cloudwatch:logs"
    name      = "RetentionInDays"
    value     = "30"
  }

  # ── Docker ────────────────────────────────────────────────────────────────
  # EB Docker platform builds from the Dockerfile included in the app bundle.
  # The container must listen on PORT 8080 — EB's nginx proxies 80 → 8080.

  # ── Application Environment Variables ─────────────────────────────────────
  # The server uses individual PG* variables (not a DATABASE_URL string).
  # PORT=8080 matches the EB Docker platform's default nginx proxy target.
  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "PORT"
    value     = "8080"
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "PGHOST"
    value     = var.pg_host
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "PGPORT"
    value     = tostring(var.pg_port)
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "PGUSER"
    value     = var.pg_user
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "PGPASSWORD"
    value     = var.pg_password
  }

  setting {
    namespace = "aws:elasticbeanstalk:application:environment"
    name      = "PGDATABASE"
    value     = var.pg_database
  }

  depends_on = [
    aws_iam_role_policy_attachment.eb_web_tier,
    aws_iam_role_policy_attachment.ssm_managed,
    aws_iam_role_policy_attachment.cloudwatch_logs,
    aws_iam_role_policy.s3_app_versions_access,
    aws_iam_instance_profile.eb_instance_profile,
  ]

  tags = var.tags
}
