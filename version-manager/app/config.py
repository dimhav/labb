"""Konfiguration for version-manager.

Laser .env-filen i projektet och exponerar:
  * komponentdefinitioner (vilka nycklar i .env som styr vad)
  * sokvagar till projekt, compose-fil och .env
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", "/workspace/project"))
ENV_FILE = PROJECT_DIR / ".env"
COMPOSE_FILE = Path(os.environ.get("COMPOSE_FILE", str(PROJECT_DIR / "docker-compose.yml")))
COMPOSE_PROJECT_NAME = os.environ.get("COMPOSE_PROJECT_NAME", "pgsqlmesh")
MANAGED_SERVICES = [
    s.strip() for s in os.environ.get("MANAGED_SERVICES", "postgres,superset,sqlmesh").split(",") if s.strip()
]


@dataclass
class Component:
    """En komponent vars version skall kontrolleras."""

    key: str                 # identifierare, t.ex. "postgres"
    name: str                # visningsnamn
    role: str                # kort beskrivning av rollen i stacken
    env_key: str             # nyckel i .env
    source: str              # "docker" eller "pypi"
    service: str             # compose-tjanst
    package: str             # image-namn eller pypi-paket
    channel: dict = field(default_factory=dict)
    upgrade_notes: str = ""
    local_build: bool = False  # byggs tjansten lokalt av docker compose?


COMPONENTS: list[Component] = [
    Component(
        key="postgres",
        name="PostgreSQL",
        role="Datalager (raw.* + analytics.*) och Supersets metadata-databas",
        env_key="POSTGRES_IMAGE",
        source="docker",
        service="postgres",
        package="library/postgres",
        channel={"kind": "semver", "image": "library/postgres", "major": 17},
        upgrade_notes=(
            "Postgres minor-uppdateringar (17.x) ar binarkompatibla och kan "
            "appliceras direkt. En major-uppgradering (t.ex. 17 -> 18) kraver "
            "pg_upgrade eller dump/restore."
        ),
    ),
    Component(
        key="sqlmesh",
        name="SQLMesh",
        role="Transformationslager: bygger analytics.* fran raw.*",
        env_key="SQLMESH_VERSION",
        source="pypi",
        service="sqlmesh",
        package="sqlmesh",
        channel={"kind": "pypi"},
        local_build=True,
        upgrade_notes=(
            "SQLMesh ar fore 1.0 och slapper ofta brytande andringar i "
            "minor-versioner. Las release notes innan uppdatering."
        ),
    ),
    Component(
        key="superset",
        name="Apache Superset",
        role="BI-lager: dashboards och utforskning av analytics.*",
        env_key="SUPERSET_IMAGE",
        source="docker",
        service="superset",
        package="apache/superset",
        channel={"kind": "pypi_docker", "image": "apache/superset", "pypi": "apache-superset"},
        local_build=True,
        upgrade_notes=(
            "Superset kraver databasmigrering (superset db upgrade) vid "
            "versionsbyte. Gors automatiskt av tjanstens bootstrap."
        ),
    ),
]

COMPONENTS_BY_KEY = {c.key: c for c in COMPONENTS}
