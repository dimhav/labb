"""HTTP-API for version-manager.

Endpoints:
  GET  /                - webbgranssnittet (statisk HTML)
  GET  /api/status      - tjansternas driftstatus
  POST /api/check       - kontrollerar versioner + sakerhetsrisker
  POST /api/upgrade     - utfor uppdatering (streamar logg, SSE)
  GET  /api/health      - enkel halsa for tjansten sjalv
"""
from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import db, envfile, registries, security, upgrader
from .cache import version_cache
from .config import COMPONENTS, COMPONENTS_BY_KEY, MANAGED_SERVICES, PROJECT_DIR

app = FastAPI(title="pgsqlmesh portal", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "version-manager" / "static")), name="static")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(PROJECT_DIR / "version-manager" / "static" / "index.html"))


@app.get("/api/overview")
async def overview() -> dict:
    """Samlad oversikt for portalen: tjanster, versioner och datalager."""
    services = await upgrader.stack_status()
    declared = envfile.read_component_versions()
    running = await upgrader.running_versions()
    try:
        stats = db.warehouse_stats()
    except Exception as exc:  # noqa: BLE001
        stats = {"error": str(exc)}
    return {
        "services": services,
        "managed": MANAGED_SERVICES,
        "versions": declared,
        "running_versions": running,
        "warehouse": stats,
    }


@app.get("/api/data/tables")
async def data_tables() -> dict:
    """Listar tabeller i raw.* och analytics.*."""
    try:
        return {"tables": db.list_tables()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Kunde inte lasa datalagret: {exc}") from exc


@app.get("/api/data/{schema}/{table}")
async def data_preview(schema: str, table: str, limit: int = 25) -> dict:
    """Visar de forsta raderna i en tabell."""
    try:
        return db.preview_table(schema, table, limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Kunde inte lasa tabellen: {exc}") from exc


@app.get("/api/status")
async def status() -> dict:
    services = await upgrader.stack_status()
    return {"services": services, "managed": MANAGED_SERVICES}


@app.post("/api/check")
async def check() -> StreamingResponse:
    """Kontrollerar alla komponenter och streamar resultatet (SSE).

    Varje komponent skickas sa snart den ar analyserad, sa att granssnittet
    kan visa resultat fortlopande (CVE-skanningen tar en stund).

    Utgangspunkten ar den version tjansten FAKTISKT kor (inte vad .env sager),
    sa att resultatet speglar driften. .env anvands bara som fallback.
    """
    declared = envfile.read_component_versions()
    running = await upgrader.running_versions()

    def current_of(component) -> str:
        return running.get(component.service) or declared.get(component.key, "")

    async def event_stream():
        totals = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
        components: list[dict] = []
        yield _sse({"type": "start"})

        async with httpx.AsyncClient() as client:
            coros = [_analyse_one(client, c, current_of(c)) for c in COMPONENTS]
            for future in asyncio.as_completed(coros):
                card = await future
                # Flagga om .env och den korande versionen inte stammer.
                declared_v = declared.get(card["key"], "")
                if declared_v and card.get("current") and declared_v != card["current"]:
                    card["declared"] = declared_v
                    card["drift"] = True
                components.append(card)
                for sev, n in (card.get("severity_counts") or {}).items():
                    totals[sev] = totals.get(sev, 0) + n
                yield _sse({"type": "component", "component": card})

        upgradable = [c["key"] for c in components if c.get("upgrade_available")]
        yield _sse(
            {
                "type": "done",
                "totals": totals,
                "upgradable": upgradable,
                "summary": _summary(components, totals),
            }
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _analyse_one(client: httpx.AsyncClient, component, current: str) -> dict:
    """Analyserar en komponent och fangar fel sa att ett kort alltid returneras."""
    try:
        return await _analyse(client, component, current)
    except Exception as exc:  # noqa: BLE001
        return {
            "key": component.key,
            "name": component.name,
            "role": component.role,
            "service": component.service,
            "source": component.source,
            "package": component.package,
            "current": current,
            "findings": [],
            "severity_counts": {},
            "recommended": None,
            "latest": None,
            "latest_released": None,
            "upgrade_available": False,
            "residual": None,
            "actions": [],
            "error": f"Kunde inte analysera: {exc}",
        }


async def _analyse(client: httpx.AsyncClient, component, current: str) -> dict:
    """Analyserar en enskild komponent."""
    out: dict = {
        "key": component.key,
        "name": component.name,
        "role": component.role,
        "service": component.service,
        "source": component.source,
        "package": component.package,
        "current": current,
        "upgrade_notes": component.upgrade_notes,
        "findings": [],
        "severity_counts": {},
        "recommended": None,
        "latest": None,
        "latest_released": None,
        "upgrade_available": False,
        "residual": None,
        "error": None,
    }

    # 1. Senaste tillgangliga version (cachas - andras langsamt).
    cached = version_cache.get(component.key)
    if cached is not None:
        latest, released = cached
    else:
        try:
            latest, released = await registries.resolve_latest(client, component)
        except registries.RegistryError as exc:
            out["error"] = str(exc)
            latest, released = None, None
        else:
            version_cache.set(component.key, (latest, released))
    out["latest"] = latest
    out["latest_released"] = released

    # 2. CVE-skanning av nuvarande version.
    findings = await security.scan_component(client, component, current)
    out["findings"] = findings
    out["severity_counts"] = security.severity_counts(findings)

    # 3. Rekommendation + kontroll av kvarvarande risk efter uppdatering.
    if latest and current and latest != current:
        out["upgrade_available"] = True
        out["recommended"] = latest
        try:
            after = await security.scan_component(client, component, latest)
            out["residual"] = {
                "version": latest,
                "severity_counts": security.severity_counts(after),
                "total": len(after),
            }
        except Exception:  # noqa: BLE001
            out["residual"] = None
    elif latest and current == latest:
        out["recommended"] = latest

    out["actions"] = _actions(component, out)
    return out


def _actions(component, out: dict) -> list[dict]:
    """Bygger tydliga atgardsforslag."""
    actions: list[dict] = []
    counts = out.get("severity_counts") or {}
    critical = counts.get("CRITICAL", 0)
    high = counts.get("HIGH", 0)
    total = sum(counts.values())

    if out.get("upgrade_available"):
        residual = out.get("residual") or {}
        rcounts = residual.get("severity_counts") or {}
        rcritical = rcounts.get("CRITICAL", 0)
        rhigh = rcounts.get("HIGH", 0)
        removes = total - residual.get("total", 0)
        priority = "critical" if critical else ("high" if high else "normal")

        detail = (
            f"Uppdatera {component.name} {out['current']} -> {out['recommended']}."
        )
        if total:
            detail += (
                f" Nuvarande version har {total} kand(a) sarbarhet(er)"
                f" ({critical} kritiska, {high} hoga)."
            )
        if residual:
            if residual.get("total", 0) == 0:
                detail += " Uppdateringen ratar samtliga kanda problem."
            else:
                detail += (
                    f" Efter uppdatering kvarstar {residual['total']} post(er)"
                    f" ({rcritical} kritiska, {rhigh} hoga)."
                )
            if removes:
                detail += f" {removes} fynd tas bort."

        actions.append(
            {
                "type": "upgrade",
                "priority": priority,
                "title": f"Uppdatera till {out['recommended']}",
                "detail": detail,
                "target": out["recommended"],
                "removes_findings": removes,
            }
        )
    elif total == 0:
        actions.append(
            {
                "type": "ok",
                "priority": "none",
                "title": "Inga kanda sarbarheter",
                "detail": f"{component.name} {out['current']} har inga kanda CVE:er i OSV/NVD.",
            }
        )
    else:
        actions.append(
            {
                "type": "review",
                "priority": "high" if (critical or high) else "normal",
                "title": "Granska manuellt",
                "detail": (
                    f"{component.name} {out['current']} har {total} kand(a) sarbarhet(er)"
                    " men ingen nyare version hittades i samma kanal."
                ),
            }
        )

    if component.upgrade_notes and out.get("upgrade_available"):
        actions.append(
            {
                "type": "info",
                "priority": "info",
                "title": "Att beakta",
                "detail": component.upgrade_notes,
            }
        )
    return actions


def _summary(components: list[dict], totals: dict) -> str:
    n_upgradable = sum(1 for c in components if c.get("upgrade_available"))
    total_findings = sum(totals.values())
    if total_findings == 0 and n_upgradable == 0:
        return "Alla komponenter ar uppdaterade och inga kanda sarbarheter hittades."
    parts = []
    if total_findings:
        parts.append(
            f"{total_findings} kanda sarbarhet(er) totalt "
            f"({totals.get('CRITICAL', 0)} kritiska, {totals.get('HIGH', 0)} hoga)"
        )
    if n_upgradable:
        parts.append(f"{n_upgradable} komponent(er) kan uppdateras")
    return ". ".join(parts) + "."


@app.post("/api/upgrade")
async def upgrade(payload: dict) -> StreamingResponse:
    """Utfor en uppdatering. Body: {"key": "...", "target": "..."}."""
    key = (payload or {}).get("key")
    target = (payload or {}).get("target")
    component = COMPONENTS_BY_KEY.get(key)
    if component is None:
        raise HTTPException(status_code=400, detail=f"Okand komponent: {key}")
    if component.service not in MANAGED_SERVICES:
        raise HTTPException(status_code=400, detail=f"Tjansten {component.service} ar inte hanterad")
    if not target:
        raise HTTPException(status_code=400, detail="target-version saknas")

    async def event_stream():
        yield _sse({"type": "start", "key": key, "target": target})
        try:
            async for line in upgrader.upgrade_component(component, target):
                yield _sse({"type": "log", "line": line})
            yield _sse({"type": "done", "ok": True})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "done", "ok": False, "error": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"
