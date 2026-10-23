#!/bin/sh
# Runs on every container start (docker-compose and k8s alike): apply any
# pending migrations before gunicorn starts serving traffic, then hand off
# to whatever CMD was passed (see Dockerfile).
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

exec "$@"
