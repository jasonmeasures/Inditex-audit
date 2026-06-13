# ── Backend — Elastic Beanstalk ────────────────────────────────────────────
output "backend_app_name" {
  description = "Elastic Beanstalk application name"
  value       = module.beanstalk_backend.application_name
}

output "backend_env_name" {
  description = "Elastic Beanstalk environment name"
  value       = module.beanstalk_backend.environment_name
}

output "backend_url" {
  description = "App public URL (dashboard accessible at this address)"
  value       = "http://${module.beanstalk_backend.endpoint_url}"
}

output "app_versions_bucket" {
  description = "S3 bucket for EB application version artifacts"
  value       = module.beanstalk_backend.app_versions_bucket_name
}

# ── Deployment helper ──────────────────────────────────────────────────────
output "deploy_commands" {
  description = "Quick-reference commands to deploy the backend"
  value       = <<-EOT
    # ── Package app (from repo root) ──────────────────────────────────────
    cd applications/Inditex-audit-main
    zip -r deploy.zip \
      Dockerfile \
      Dockerrun.aws.json \
      inditex_audit_server.py \
      inditex_audit_dashboard.html \
      requirements.txt

    # ── Upload to S3 ─────────────────────────────────────────────────────
    aws s3 cp deploy.zip \
      s3://${module.beanstalk_backend.app_versions_bucket_name}/deploy.zip

    # ── Create & deploy application version ───────────────────────────────
    VERSION="v$(date +%Y%m%d%H%M%S)"
    aws elasticbeanstalk create-application-version \
      --application-name ${module.beanstalk_backend.application_name} \
      --version-label $VERSION \
      --source-bundle S3Bucket=${module.beanstalk_backend.app_versions_bucket_name},S3Key=deploy.zip

    aws elasticbeanstalk update-environment \
      --environment-name ${module.beanstalk_backend.environment_name} \
      --version-label $VERSION
  EOT
}
