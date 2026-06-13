# Terraform Backend Setup — Inditex Audit

State is stored in S3 with native locking. Run these commands **once** before the first `terraform init`.

## Create the S3 state bucket

```bash
aws s3api create-bucket \
  --bucket inditex-audit-terraform-state \
  --region us-west-2 \
  --create-bucket-configuration LocationConstraint=us-west-2

aws s3api put-bucket-versioning \
  --bucket inditex-audit-terraform-state \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket inditex-audit-terraform-state \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-public-access-block \
  --bucket inditex-audit-terraform-state \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

## First apply

The Inditex app deploys directly into the shared `kn-playground-dev-vpc` — no VPC peering needed.
You must apply shared-infra first so the public subnet and IGW exist.

### Step 1 — apply shared-infra (adds IGW + public subnet to shared VPC)

```bash
cd applications/shared-infra/terraform/envs/dev
terraform apply
```

Collect the outputs you need for Inditex:

```bash
terraform output -raw shared_vpc_id
terraform output -json public_subnet_ids
terraform output -raw rds_endpoint
terraform output -raw rds_master_password
```

### Step 2 — apply Inditex

```bash
cd applications/Inditex-audit-main/terraform/envs/dev
cp terraform.tfvars.example terraform.tfvars
# Fill in: vpc_id, subnet_ids, pg_host, pg_password

terraform init
terraform apply
```

## Deploy the app

After infrastructure is created, build and upload the app bundle:

```bash
cd applications/Inditex-audit-main

zip -r deploy.zip \
  Dockerfile \
  inditex_audit_server.py \
  inditex_audit_dashboard.html \
  requirements.txt

APP_VERSIONS_BUCKET=$(cd terraform/envs/dev && terraform output -raw app_versions_bucket)
APP_NAME=$(cd terraform/envs/dev && terraform output -raw backend_app_name)
ENV_NAME=$(cd terraform/envs/dev && terraform output -raw backend_env_name)
VERSION="v$(date +%Y%m%d%H%M%S)"

aws s3 cp deploy.zip s3://$APP_VERSIONS_BUCKET/deploy.zip

aws elasticbeanstalk create-application-version \
  --application-name $APP_NAME \
  --version-label $VERSION \
  --source-bundle S3Bucket=$APP_VERSIONS_BUCKET,S3Key=deploy.zip

aws elasticbeanstalk update-environment \
  --environment-name $ENV_NAME \
  --version-label $VERSION
```

The dashboard will be accessible at the `backend_url` Terraform output.
