#!/usr/bin/env bash
# ===========================================================================
#  Superset-start: migrerar metadata-databasen, skapar admin, registrerar
#  datalagret (analytics.*) och startar servern.
# ===========================================================================
set -euo pipefail

PY=/app/.venv/bin/python
SUPERSET=/app/.venv/bin/superset

echo "Vantar pa Postgres ..."
until "$PY" - <<'EOF'
import os, sys
import psycopg2
try:
    psycopg2.connect(
        host="postgres", port=5432,
        user=os.environ.get("SUPERSET_DB_USER", "superset"),
        password=os.environ.get("SUPERSET_DB_PASSWORD", "superset"),
        dbname=os.environ.get("SUPERSET_DB", "superset"),
    ).close()
except Exception:
    sys.exit(1)
EOF
do
    sleep 2
done

echo "Migrerar metadata-databasen ..."
"$SUPERSET" db upgrade

echo "Skapar/uppdaterar admin-anvandare ..."
"$SUPERSET" fab create-admin \
    --username "${SUPERSET_ADMIN_USER:-admin}" \
    --firstname Superset \
    --lastname Admin \
    --email "admin@example.com" \
    --password "${SUPERSET_ADMIN_PASSWORD:-admin}" || true

"$SUPERSET" init

echo "Registrerar datalager + dataset + dashboard ..."
"$PY" /app/pgsqlmesh-setup-assets.py

echo "Startar Superset."
exec /app/docker/entrypoints/run-server.sh
