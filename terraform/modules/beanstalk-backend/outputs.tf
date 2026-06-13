output "application_name" {
  description = "Elastic Beanstalk application name"
  value       = aws_elastic_beanstalk_application.backend.name
}

output "environment_name" {
  description = "Elastic Beanstalk environment name"
  value       = aws_elastic_beanstalk_environment.backend.name
}

output "endpoint_url" {
  description = "Public CNAME of the Elastic Beanstalk environment"
  value       = aws_elastic_beanstalk_environment.backend.cname
}

output "environment_id" {
  description = "Elastic Beanstalk environment ID"
  value       = aws_elastic_beanstalk_environment.backend.id
}

output "app_versions_bucket_name" {
  description = "S3 bucket name for EB application version artifacts"
  value       = aws_s3_bucket.app_versions.id
}

output "security_group_id" {
  description = "Security group ID for the backend EB environment"
  value       = aws_security_group.backend.id
}
