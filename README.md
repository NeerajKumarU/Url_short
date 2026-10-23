# DevOps Portfolio Project — URL Shortener on Kubernetes

A Django URL-shortener app, taken end-to-end through containerization,
Infrastructure as Code, Kubernetes deployment, CI/CD, and monitoring.
Built to demonstrate the DevOps lifecycle recruiters actually look for,
not just individual tool familiarity.

See [`docs/architecture.md`](docs/architecture.md) for the full diagram and design notes.

## Stack

| Layer | Tool |
|---|---|
| App | Django (Python), Postgres |
| Containers | Docker, multi-stage builds |
| Orchestration | Kubernetes (Deployment, StatefulSet, HPA, Ingress) |
| IaC | Terraform (AWS VPC + EKS + ECR) |
| CI/CD | GitHub Actions (lint → test → build → scan → push → deploy) |
| Monitoring | Prometheus, Grafana, Alertmanager |
| Security | Trivy image scanning, non-root containers, env-based secrets |

## Repo layout

```
app/            Django application (source: NeerajKumarU/Url_short)
k8s/            Kubernetes manifests (Deployment, Service, Ingress, HPA, StatefulSet)
infra/terraform/ AWS infrastructure as code (VPC, EKS, ECR)
monitoring/     Prometheus/Grafana Helm values, ServiceMonitor, alert rules
.github/workflows/ CI/CD pipeline
docs/           Architecture notes
```

## Run it locally (free, ~2 minutes)

```bash
docker compose up --build
```

Visit http://localhost:8000. Postgres data persists in a named volume
between runs.

## OrbitLink SaaS capabilities

The Django application now includes workspace RBAC, campaigns, custom domains,
smart routing, scheduling, A/B tests, conversions, approvals, audit logs,
destination safety, abuse reports, bot classification, API keys, signed
webhooks, atomic CSV imports, periodic analytics refresh, trusted-edge geo
fields, retention controls, explainable anomaly findings, email notifications,
and authorization-scoped AI assistants.

Copy `.env.example` when preparing an environment. AI and real SMTP delivery
are optional: without an AI key the UI says the feature is unavailable, and
local email uses Django's console backend.

Useful application commands from `app/`:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test
python manage.py process_operations
```

Run `process_operations` on a scheduler (for example every five minutes) to
retry eligible webhook deliveries, scan explainable traffic rules, anonymize
expired IP data, and send lifecycle notifications. No queue service is required;
the command is deliberately ready to move behind a worker later.

Workspace administration pages include:

- `/dashboard/`, `/campaigns/`, `/domains/`, `/approvals/`
- `/integrations/api-keys/`, `/integrations/webhooks/`
- `/tools/bulk-import/`, `/analytics/anomalies/`
- `/ai/analytics/`, `/ai/campaign-suggestions/`

Platform staff pages include `/admin-dashboard/`,
`/admin-dashboard/reports/`, and `/admin-dashboard/ai-abuse/`.

## Deploy to a real cluster

**Option A — local Kubernetes (free):** `kind` or `minikube` instead of EKS.
Build the image, load it into the cluster (`kind load docker-image ...`),
then apply the manifests below.

**Option B — cloud (small cost, see `infra/terraform/README.md`):**

```bash
# 1. Provision infrastructure
cd infra/terraform
terraform init && terraform apply
aws eks update-kubeconfig --region ap-south-1 --name devops-portfolio

# 2. Build & push the image (or let CI/CD do this on push to main)
cd ../../app
docker build -t ghcr.io/<you>/url-shortener:local .
docker push ghcr.io/<you>/url-shortener:local

# 3. Create secrets (never commit the real file)
cp ../k8s/secret.yaml.example ../k8s/secret.yaml
# edit k8s/secret.yaml with real values, then:
kubectl apply -f ../k8s/secret.yaml

# 4. Deploy the app
kubectl apply -f ../k8s/namespace.yaml
kubectl apply -f ../k8s/configmap.yaml
kubectl apply -f ../k8s/postgres.yaml
kubectl apply -f ../k8s/web.yaml
kubectl apply -f ../k8s/ingress.yaml

kubectl get pods -n devops-portfolio    # confirm everything is Running
```

### Monitoring

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f monitoring/prometheus-values.yaml

kubectl apply -f monitoring/service-monitor.yaml
kubectl apply -f monitoring/alert-rules.yaml

kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
# open http://localhost:3000 (admin / the password you set in prometheus-values.yaml)
```

### Tear down (don't skip this on a paid cluster)

```bash
kubectl delete -f k8s/
cd infra/terraform && terraform destroy
```

## CI/CD pipeline scaffold

The deployment design expects a `.github/workflows/ci-cd.yml` workflow, but a
workflow file is not currently bundled in this checkout. When one is added, it
should:

1. Lints and runs the Django test suite
2. Builds the Docker image
3. Scans it with Trivy for CVEs
4. Pushes to GitHub Container Registry
5. Deploys to the cluster via `kubectl set image`, behind a GitHub
   Environment approval gate

Requires these repo secrets: `KUBE_CONFIG` (base64-encoded kubeconfig).
`GITHUB_TOKEN` is provided automatically.

## What's deliberately simple (and the obvious next steps)

This project is scoped to be buildable and explainable end-to-end, not to
show every DevOps tool at once. Natural next steps, worth mentioning as
"here's what I'd add next" in an interview:

- **GitOps** — replace the `kubectl set image` deploy step with ArgoCD or
  Flux watching this repo.
- **Helm chart** — package `k8s/*.yaml` as a chart for templated,
  parameterized deploys across environments.
- **Managed database** — swap the Postgres StatefulSet for RDS once this
  needs to be more than a demo.
- **Secrets management** — Sealed Secrets or an external vault instead of
  plain Kubernetes `Secret` objects.
- **Centralized logging** — Loki or the EFK stack alongside the existing
  Prometheus/Grafana setup.

## Cost

Everything above can be run entirely locally (`docker compose`, `kind`/`minikube`)
at **$0**. A short-lived AWS demo via the included Terraform costs roughly
**$1–2/hour** — provision right before recording your demo, `terraform destroy`
immediately after. See `infra/terraform/README.md` for the exact breakdown.
