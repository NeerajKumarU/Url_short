# --- Build stage: compile deps with full build tools available ---
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# Installed into the image's global site-packages (not --user), so it's available
# to any user that later runs python — root during the build steps below, and
# appuser at container runtime — with no $HOME-dependent path to get wrong.
RUN pip install --no-cache-dir -r requirements.txt

# --- Final stage: slim runtime image, no compilers, non-root user ---
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/* \
    && addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copies both the installed packages (lib/python3.11/site-packages) and their
# console scripts (bin/gunicorn, etc.) — both live under /usr/local in this image.
COPY --from=builder /usr/local /usr/local
COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Baked-in defaults are enough for collectstatic (no DB access needed); real
# secrets/DB config are injected at runtime via ConfigMap/Secret env vars.
# Runs as root (before USER switch below) — fine, since packages are global now.
RUN python manage.py collectstatic --noinput

RUN chmod +x entrypoint.sh && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "ulrs_shortener.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
