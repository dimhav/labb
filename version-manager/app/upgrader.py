"""Utfor uppdateringar av stacken via docker compose.

Flodet vid en uppdatering av en komponent:

  1. Las den version tjansten FAKTISKT kor (fran containern).
  2. Skriv ny version till .env (single source of truth).
  3. Bygg om tjanstens image om den byggs lokalt (sqlmesh, superset).
  4. `docker compose up -d --no-deps <tjanst>` - drar ny image och
     aterstaller tjansten. Postgres-datan ligger kvar i volymen.
  5. Vanta in tjanstens healthcheck och verifiera att ratt version kor.
     Misslyckas nagot steg rullas .env tillbaka, sa att den aldrig visar
     en version som inte ar i drift.

Allt loggas radvis sa att UI:t kan visa en live-logg.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

from . import envfile
from .config import COMPOSE_FILE, COMPOSE_PROJECT_NAME, PROJECT_DIR

# Container-namn per tjanst (matchar docker-compose.yml).
CONTAINER_NAMES = {
    "postgres": "pgsqlmesh-postgres",
    "sqlmesh": "pgsqlmesh-sqlmesh",
    "superset": "pgsqlmesh-superset",
    "version-manager": "pgsqlmesh-version-manager",
}

# Lokalt byggda images (t.ex. superset) satter sin kallversion i denna label,
# eftersom deras image-tagg inte innehaller nagon version.
SOURCE_IMAGE_LABEL = "org.pgsqlmesh.source-image"


class UpgradeError(RuntimeError):
    pass


def _base_cmd() -> list[str]:
    return [
        "docker", "compose",
        "--project-name", COMPOSE_PROJECT_NAME,
        "--file", str(COMPOSE_FILE),
    ]


async def _run(cmd: list[str], *, timeout: int = 60) -> tuple[int, str]:
    """Kor ett kommando utan att streama och returnerar (slutkod, utdata)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(PROJECT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, f"[timeout efter {timeout}s]"
    return proc.returncode or 0, out.decode(errors="replace")


async def _stream(cmd: list[str], *, timeout: int = 900) -> AsyncIterator[str]:
    """Kor ett kommando och ger utdata radvis. Kastar vid fel slutkod."""
    yield f"$ {' '.join(cmd)}"
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(PROJECT_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "COMPOSE_PROGRESS": "plain"},
    )
    assert proc.stdout is not None
    try:
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            if not line:
                break
            yield line.decode(errors="replace").rstrip("\n")
    except asyncio.TimeoutError:
        proc.kill()
        yield f"[timeout efter {timeout}s - avbryter]"
    code = await proc.wait()
    yield f"[klart med slutkod {code}]"
    if code != 0:
        raise UpgradeError(f"Kommandot misslyckades (slutkod {code})")


def _tag_of(image: str) -> str:
    """Plockar ut taggen ur ett image-namn, t.ex. postgres:17.6 -> 17.6."""
    if not image:
        return ""
    last = image.rsplit("/", 1)[-1]
    if ":" in last:
        return last.rsplit(":", 1)[1]
    return "latest"


async def running_version(service: str) -> str | None:
    """Returnerar den version tjansten FAKTISKT kor, eller None om okand.

    Lokalt byggda images (superset) anger sin kallversion i en label. Ovriga
    (postgres, sqlmesh) har versionen i image-taggen.
    """
    container = CONTAINER_NAMES.get(service, service)
    code, out = await _run(
        ["docker", "inspect", "--format", "{{json .Config}}", container], timeout=30
    )
    if code != 0 or not out.strip():
        return None
    try:
        cfg = json.loads(out.strip().splitlines()[0])
    except (json.JSONDecodeError, IndexError):
        return None

    labels = cfg.get("Labels") or {}
    source = labels.get(SOURCE_IMAGE_LABEL)
    if source:
        return _tag_of(source)

    version = _tag_of(cfg.get("Image") or "")
    return version or None


async def running_versions() -> dict[str, str]:
    """Returnerar korande version per tjanst (dar den kan bestammas)."""
    out: dict[str, str] = {}
    for service in CONTAINER_NAMES:
        version = await running_version(service)
        if version:
            out[service] = version
    return out


async def _container_state(service: str) -> tuple[str, str]:
    """Returnerar (state, health) for en tjanst."""
    cmd = _base_cmd() + ["ps", "--format", "json", service]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(PROJECT_DIR),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    for line in out.decode().strip().splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("Service") == service:
            return obj.get("State", "unknown"), obj.get("Health", "")
    return "unknown", ""


async def _wait_healthy(component) -> None:
    """Vantar tills tjansten ar uppe. Kastar om den dor eller inte blir frisk."""
    for _ in range(80):
        await asyncio.sleep(3)
        state, health = await _container_state(component.service)
        if state in ("exited", "dead"):
            raise UpgradeError(
                f"Tjansten {component.service} avslutades ovantat ({state})."
            )
        # Tjanster utan healthcheck rapporterar tom health - da racker "running".
        if health == "healthy" or (state == "running" and not health):
            return
    raise UpgradeError(
        f"{component.service} rapporterade inte healthy inom tidsgransen."
    )


async def upgrade_component(component, target_version: str) -> AsyncIterator[str]:
    """Uppdaterar en komponent till target_version och streamar loggen."""
    declared = envfile.read_component_versions().get(component.key, "")
    running = await running_version(component.service)

    if running == target_version and declared == target_version:
        yield f"{component.name} ar redan pa {target_version} - inget att gora."
        return

    if running and declared and running != declared:
        yield (
            f"[varning] .env anger {declared} men tjansten kor {running}. "
            "Tjansten startas om for att stamma."
        )

    yield f"Uppdaterar {component.name}: {running or declared or '?'} -> {target_version}"

    # 1. Spara nuvarande .env-varde och skriv ny version.
    orig_raw = envfile.read_env().get(component.env_key, "")
    value = envfile.build_env_value(component, target_version)
    envfile.update_env_version(component.env_key, value)
    yield f".env uppdaterad: {component.env_key}={value}"

    try:
        # 2. Bygg om lokala images vid behov.
        if component.local_build:
            yield "Bygger image ..."
            async for line in _stream(_base_cmd() + ["build", component.service]):
                yield line

        # 3. Dra ny image och aterstall tjansten. Lokalt byggda images far inte
        #    --pull - da skulle compose forsoka hamta dem fran en registry som
        #    inte finns. Flaggan maste sta fore tjanstenamnet.
        up_cmd = _base_cmd() + ["up", "-d", "--no-deps"]
        if not component.local_build:
            up_cmd += ["--pull", "always"]
        up_cmd.append(component.service)
        async for line in _stream(up_cmd):
            yield line

        # 4. Vanta in healthcheck och verifiera att ratt version faktiskt kor.
        yield "Vantar in tjanstens healthcheck ..."
        await _wait_healthy(component)

        actual = await running_version(component.service)
        if actual != target_version:
            raise UpgradeError(
                f"Verifiering misslyckades: {component.service} kor "
                f"{actual or 'okand'} men {target_version} forvantades."
            )
        yield f"{component.name} ar nu uppe pa {target_version} (verifierat)."
    except Exception:
        # Rulla tillbaka .env sa att den aldrig visar en version som inte kor.
        if orig_raw:
            envfile.update_env_version(component.env_key, orig_raw)
            yield f"[info] .env aterstalld till {component.env_key}={orig_raw}"
        raise


async def stack_status() -> list[dict]:
    """Returnerar status for alla tjanster."""
    cmd = _base_cmd() + ["ps", "--format", "json"]
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(PROJECT_DIR),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()

    services = []
    for line in out.decode().strip().splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        services.append({
            "service": obj.get("Service"),
            "state": obj.get("State"),
            "health": obj.get("Health", ""),
            "image": obj.get("Image"),
        })
    return services
