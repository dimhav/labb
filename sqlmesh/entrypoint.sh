#!/usr/bin/env bash
# ===========================================================================
#  SQLMesh-tjansten.
#
#  Vantar in Postgres, kors sedan i en loop:
#     sqlmesh plan   - skapa/uppdatera modellerna (analytics.*)
#     sqlmesh run    - materialisera senaste intervallet
#  Intervall styrs av SQLMESH_INTERVAL (sekunder).
# ===========================================================================
set -euo pipefail

echo "Vantar pa Postgres ${POSTGRES_HOST}:${POSTGRES_PORT} ..."
until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -q; do
    sleep 2
done

# Vanta tills raw-tabellerna finns (seedas av db/init).
echo "Vantar pa raw-tabellerna ..."
until psql "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}" \
        -tAc "SELECT to_regclass('raw.orders') IS NOT NULL" | grep -q t; do
    sleep 2
done

echo "SQLMesh $(sqlmesh --version 2>/dev/null || echo "$SQLMESH_VERSION") startar."

# Vid versionsbyte kan SQLMesh:s tillstandstabeller behova migreras.
# 'migrate' ar idempotent och gor inget om ingen migrering behovs.
if ! sqlmesh plan --auto-apply --no-prompts 2>&1 | tee /tmp/sqlmesh-plan.log; then
    if grep -q "migration" /tmp/sqlmesh-plan.log; then
        echo "Kor sqlmesh migrate (versionsbyte upptackt) ..."
        sqlmesh migrate
        sqlmesh plan --auto-apply --no-prompts
    else
        sqlmesh plan --no-prompts
    fi
fi

INTERVAL="${SQLMESH_INTERVAL:-300}"
echo "Kor loop var ${INTERVAL}:e sekund."
while true; do
    sqlmesh run || echo "sqlmesh run misslyckades, forsoker igen senare"
    sleep "$INTERVAL"
done
