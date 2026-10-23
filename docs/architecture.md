# Architecture

## What this is

A Django URL-shortener app (originally [NeerajKumarU/Url_short](https://github.com/NeerajKumarU/Url_short)),
taken through a full DevOps lifecycle: containerized, deployed to Kubernetes
via Infrastructure as Code, shipped through an automated CI/CD pipeline, and
observed with Prometheus/Grafana.

## Diagram

```
                      ┌─────────────────────┐
  git push  ───────▶  │   GitHub Actions     │
                      │  lint → test → build  │
                      │  → scan → push image  │
                      │  → deploy (kubectl)    │
                      └──────────┬───────────┘
                                 │ image push
                                 ▼
                      ┌─────────────────────┐
                      │  GHCR (image registry)│
                      └──────────┬───────────┘
                                 │ pulled by
                                 ▼
 ┌──────────────────────────────────────────────────────────┐
 │  Kubernetes cluster (EKS, provisioned by Terraform)        │
 │                                                            │
 │   Ingress ──▶ Service (web) ──▶ Deployment (web, 2 pods)   │
 │                                      │   Django + gunicorn  │
 │                                      ▼                      │
 │                            StatefulSet (postgres)           │
 │                                                            │
 │   Prometheus ◀── scrapes /metrics on web pods               │
 │   Grafana    ◀── dashboards from Prometheus                 │
 │   Alertmanager ◀── fires on PodCrashLooping, AppDown, etc.  │
 └──────────────────────────────────────────────────────────┘
```

## Request flow

1. A visitor hits the Ingress host.
2. Ingress routes to the `web` Service, which load-balances across the Django pods.
3. Django serves the home page, creates short URLs (`POST /shorturl`), or
   redirects a visitor from a short code (`GET /<shorturl>`), reading/writing
   Postgres each time.
4. `/health` and `/ready` back the pod's liveness/readiness probes;
   `/metrics` is scraped by Prometheus every 15s.

## Link analytics and privacy

Each successful, non-expired short-link redirect increments the link's lifetime
counter and creates a small `ClickEvent` row. Events contain the request time,
the server-observed remote IP address, a truncated user-agent and referrer, plus
coarse browser, device, operating-system, and referrer classifications. Raw IP
addresses are retained for operational analysis but are never displayed in the
user dashboard. The application deliberately ignores untrusted
`X-Forwarded-For` values; a production deployment should add explicit trusted
proxy handling and a documented retention policy before using forwarded IPs.

Analytics are only available through owner-scoped authenticated views. Expired
links return HTTP 410 and do not increment counters or create events.

## Why these choices

- **StatefulSet for Postgres, not a managed DB** — keeps the whole stack
  reproducible from the manifests alone, with no external account to set up.
  (Swapping in RDS is a one-line call-out in interviews: "I'd move this to a
  managed database for anything beyond a demo, here's why.")
- **Two replicas + HPA on the Django Deployment** — the app is stateless
  (session/db state lives in Postgres), so it scales horizontally for free.
- **Whitenoise instead of a separate nginx/static pod** — one fewer moving
  part for an app this size; static assets are served straight from gunicorn.
- **Hand-rolled `/metrics` instead of a client library** — keeps the base
  image small and the metrics format is a two-minute read, but the natural
  next step (noted in the README) is `django-prometheus` for real histograms.

## Known trade-offs (worth being upfront about in an interview)

- Secrets are Kubernetes `Secret` objects, not integrated with a vault —
  fine for a portfolio project, a gap you'd close in a real company.
- The CI/CD pipeline deploys with `kubectl set image` rather than GitOps
  (ArgoCD/Flux). The README's "Next steps" section covers upgrading to that.
- Single NAT gateway / single-AZ-leaning setup in Terraform — a deliberate
  cost trade-off for a demo cluster, not a production HA setup.
