#!/usr/bin/env bash
# ============================================================
# Inditex Audit — Deploy Script
# Zips the app + Dockerfile and deploys to Elastic Beanstalk.
# EB builds the Docker image on the instance from the bundle.
#
# Usage:
#   ./deploy.sh
#
# Prerequisites:
#   - AWS CLI configured
#   - Terraform has been applied (infrastructure exists)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/terraform/envs/dev"

echo "=================================================="
echo " Inditex Audit — Deploy"
echo "=================================================="

# ── Check dependencies ────────────────────────────────────────────────────
for cmd in aws zip terraform; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "  '$cmd' is not installed. Please install it first."
    exit 1
  fi
done

# ── Read Terraform outputs ────────────────────────────────────────────────
echo ""
echo "→ Reading infrastructure outputs from Terraform..."
cd "$TF_DIR"

EB_APP_NAME=$(terraform output -raw backend_app_name 2>/dev/null)
EB_ENV_NAME=$(terraform output -raw backend_env_name 2>/dev/null)
S3_BUCKET=$(terraform output -raw app_versions_bucket 2>/dev/null)
AWS_REGION=$(grep '^aws_region' terraform.tfvars 2>/dev/null | awk -F'"' '{print $2}')
AWS_REGION="${AWS_REGION:-us-west-2}"

if [[ -z "$EB_APP_NAME" || -z "$S3_BUCKET" ]]; then
  echo "  Could not read Terraform outputs."
  echo "  Make sure 'terraform apply' has completed successfully."
  exit 1
fi

echo "   EB Application : $EB_APP_NAME"
echo "   EB Environment : $EB_ENV_NAME"
echo "   S3 Bucket      : $S3_BUCKET"
echo "   AWS Region     : $AWS_REGION"

# ── Build deployment bundle ───────────────────────────────────────────────
VERSION="v$(date +%Y%m%d%H%M%S)"
ZIPFILE="/tmp/inditex-audit-${VERSION}.zip"

echo ""
echo "→ Creating deployment bundle ($VERSION)..."
cd "$SCRIPT_DIR"

zip -q "$ZIPFILE" \
  Dockerfile \
  Dockerrun.aws.json \
  inditex_audit_server.py \
  inditex_audit_dashboard.html \
  requirements.txt

zip -qr "$ZIPFILE" .platform/

echo "   Created $(basename "$ZIPFILE") ($(du -sh "$ZIPFILE" | cut -f1))"

# ── Upload to S3 ──────────────────────────────────────────────────────────
S3_KEY="deploy-${VERSION}.zip"

echo ""
echo "→ Uploading to S3 (s3://$S3_BUCKET/$S3_KEY)..."
aws s3 cp "$ZIPFILE" "s3://${S3_BUCKET}/${S3_KEY}" \
  --region "$AWS_REGION" \
  --no-progress
echo "   Upload complete"

# ── Create EB application version ─────────────────────────────────────────
echo ""
echo "→ Creating Elastic Beanstalk application version ($VERSION)..."
aws elasticbeanstalk create-application-version \
  --application-name "$EB_APP_NAME" \
  --version-label    "$VERSION" \
  --source-bundle    S3Bucket="$S3_BUCKET",S3Key="$S3_KEY" \
  --region           "$AWS_REGION" \
  --output json > /dev/null
echo "   Application version created"

# ── Deploy to environment ─────────────────────────────────────────────────
echo ""
echo "→ Deploying to environment ($EB_ENV_NAME)..."
aws elasticbeanstalk update-environment \
  --environment-name "$EB_ENV_NAME" \
  --version-label    "$VERSION" \
  --region           "$AWS_REGION" \
  --output json > /dev/null
echo "   Deployment triggered"

# ── Poll for completion ───────────────────────────────────────────────────
fetch_eb_events() {
  echo ""
  echo "→ Recent Elastic Beanstalk events:"
  aws elasticbeanstalk describe-events \
    --environment-name "$EB_ENV_NAME" \
    --region "$AWS_REGION" \
    --max-items 20 \
    --query "Events[].[EventDate,Message]" \
    --output text 2>/dev/null | head -20 || true
}

echo ""
echo "→ Waiting for environment to become healthy..."
TIMEOUT=300
ELAPSED=0
INTERVAL=15

while [[ $ELAPSED -lt $TIMEOUT ]]; do
  ENV_STATUS=$(aws elasticbeanstalk describe-environments \
    --environment-names "$EB_ENV_NAME" \
    --region "$AWS_REGION" \
    --query "Environments[0].Status" \
    --output text)

  HEALTH=$(aws elasticbeanstalk describe-environments \
    --environment-names "$EB_ENV_NAME" \
    --region "$AWS_REGION" \
    --query "Environments[0].HealthStatus" \
    --output text)

  echo "   Status: $ENV_STATUS | Health: $HEALTH"

  if [[ "$ENV_STATUS" == "Ready" ]]; then
    if [[ "$HEALTH" == "Ok" || "$HEALTH" == "Unknown" ]]; then
      echo "   Environment is Ready!"
      break
    fi
    if [[ "$HEALTH" == "Degraded" || "$HEALTH" == "Severe" ]]; then
      echo "   Environment is Ready but health is $HEALTH — fetching events..."
      fetch_eb_events
      exit 1
    fi
  fi

  if [[ "$ENV_STATUS" == "Terminated" ]]; then
    echo "   Environment was terminated unexpectedly."
    fetch_eb_events
    exit 1
  fi

  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done

if [[ $ELAPSED -ge $TIMEOUT ]]; then
  echo "   Timed out waiting for healthy status."
  fetch_eb_events
  exit 1
fi

# ── Print result ──────────────────────────────────────────────────────────
cd "$TF_DIR"
APP_URL=$(terraform output -raw backend_url 2>/dev/null)

echo ""
echo "=================================================="
echo "  Deployed successfully!"
echo ""
echo "   Version : $VERSION"
echo "   URL     : $APP_URL"
echo "   Health  : $APP_URL/api/health"
echo ""
echo "   Test it:"
echo "   curl $APP_URL/api/health"
echo "=================================================="

# ── Cleanup ───────────────────────────────────────────────────────────────
rm -f "$ZIPFILE"
