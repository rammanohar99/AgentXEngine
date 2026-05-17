# Kubernetes Manifests

Kubernetes deployment manifests for production-scale deployments.

For most use cases, Cloud Run (`infrastructure/cloudrun/`) is simpler and recommended.
Use Kubernetes when you need:
- Custom networking (VPC-native clusters)
- GPU workloads for local model inference
- Fine-grained resource quotas
- Multi-region active-active deployments

## Structure (to be implemented in Phase 5+)

```
k8s/
  base/
    backend-deployment.yaml
    backend-service.yaml
    frontend-deployment.yaml
    frontend-service.yaml
    worker-deployment.yaml
    postgres-statefulset.yaml
    redis-statefulset.yaml
  overlays/
    development/
    staging/
    production/
```

## Prerequisites

- GKE cluster with Workload Identity enabled
- Cloud SQL Auth Proxy sidecar for database connections
- Secret Manager for secrets (not Kubernetes Secrets)
