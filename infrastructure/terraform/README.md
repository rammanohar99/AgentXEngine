# Terraform Infrastructure

Infrastructure-as-code for provisioning the AI Engineering OS cloud resources.

## Resources (to be implemented)

```
terraform/
  main.tf           — Provider config, backend state
  variables.tf      — Input variables
  outputs.tf        — Output values
  modules/
    database/       — Cloud SQL PostgreSQL + pgvector extension
    redis/          — Memorystore Redis
    cloudrun/       — Cloud Run services (backend, frontend)
    artifact_registry/ — Docker image registry
    iam/            — Service accounts and IAM bindings
    secrets/        — Secret Manager secrets
    vpc/            — VPC network and subnets
```

## Quick Start (when implemented)

```bash
cd infrastructure/terraform
terraform init
terraform plan -var="project_id=my-project"
terraform apply -var="project_id=my-project"
```

## State Backend

Use Google Cloud Storage for remote state:

```hcl
terraform {
  backend "gcs" {
    bucket = "my-project-terraform-state"
    prefix = "aiengos"
  }
}
```
