#!/usr/bin/env bash
# ===========================================================================
#  Skapar Supersets metadata-databas och roll.
#  Kors automatiskt av Postgres-imagen vid forsta starten.
# ===========================================================================
set -euo pipefail

SUPERSET_DB="${SUPERSET_DB:-superset}"
SUPERSET_DB_USER="${SUPERSET_DB_USER:-superset}"
SUPERSET_DB_PASSWORD="${SUPERSET_DB_PASSWORD:-superset}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v superset_db="$SUPERSET_DB" \
     -v superset_user="$SUPERSET_DB_USER" \
     -v superset_password="$SUPERSET_DB_PASSWORD" <<-'EOSQL'
    SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'superset_user', :'superset_password')
    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'superset_user') \gexec

    SELECT format('CREATE DATABASE %I OWNER %I', :'superset_db', :'superset_user')
    WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'superset_db') \gexec

    SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'superset_db', :'superset_user') \gexec
EOSQL

echo "Superset-metadata klar: databas='${SUPERSET_DB}' roll='${SUPERSET_DB_USER}'"
