#!/usr/bin/env bash
# ===========================================================================
#  Snabbstart for pgsqlmesh.
#
#  Gor tre saker:
#    1. Skapar .env fran .env.example om den saknas.
#    2. Rensar versionsvariabler ur skalet (de overskuggar annars .env och
#       kan starta tjansterna med fel version).
#    3. Bygger och startar hela stacken.
#
#  Kor:  ./start.sh
# ===========================================================================
set -euo pipefail

cd "$(dirname "$0")"

# 1. .env maste finnas - den ar gitignorerad (innehaller losenord).
if [ ! -f .env ]; then
    echo "Skapar .env fran .env.example ..."
    cp .env.example .env
    echo "  Klart. Byt garna losenord i .env innan produktion."
fi

# 2. Skalvariabler vinner over .env - ta bort dem sa ratt version startar.
unset POSTGRES_IMAGE SQLMESH_VERSION SUPERSET_IMAGE || true

# 3. Starta.
echo "Bygger och startar stacken (forsta gangen tar nagra minuter) ..."
docker compose up -d --build

echo
echo "Klart. Tjansterna startar i ordning:"
echo "  Portal:   http://localhost:12000"
echo "  Superset: http://localhost:12001  (admin / admin)"
echo
echo "Folj starten med:  docker compose ps"
