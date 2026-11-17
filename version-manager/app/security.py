"""Sakerhetsskanning av komponentversioner.

Tva kall anvands for att hitta kand sarbarhet (CVE):

  * OSV.dev  - bra for PyPI-paket (SQLMesh, Superset). Returnerar aven
               "fixed"-versioner, dvs vilken version som ratar problemet.
  * NVD (NIST) - CPE-baserad matchning. Anvands for Docker-images
               (Postgres, Superset) dar OSV saknar tackning.

Resultatet ar en lista av Finding-objekt med allvarlighetsgrad, CVSS-poang,
referenser och - nar det gar - vilken version som ratar problemet.
"""
from __future__ import annotations

import asyncio
import re

import httpx
from packaging.version import InvalidVersion, Version

from .cache import scan_cache

OSV_QUERY = "https://api.osv.dev/v1/query"
NVD_CVE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_UA = {"User-Agent": "pgsqlmesh-version-manager/1.0"}

# NVD tillater fa anrop per tidsenhet - serialisera dem globalt.
_NVD_LOCK = asyncio.Lock()

# CPE-produktnamn for varje komponent (for NVD-sokning).
CPE_PRODUCTS = {
    "postgres": "cpe:2.3:a:postgresql:postgresql",
    "superset": "cpe:2.3:a:apache:superset",
}

SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0, "NONE": 0}


def parse_version(value: str) -> Version | None:
    """Tolerant versionsparsning - returnerar None om vardet inte gar att tolka."""
    if not value:
        return None
    try:
        return Version(value)
    except InvalidVersion:
        return None


def _severity_from_score(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    if score > 0.0:
        return "LOW"
    return "NONE"


class Finding(dict):
    """Ett sakerhetsfynd. Ar en dict for enkel JSON-serialisering."""


def _finding(
    *, cve_id: str, summary: str, severity: str, score: float | None,
    source: str, fixed_in: str | None, references: list[str],
) -> Finding:
    sev = (severity or "UNKNOWN").upper()
    sev = "MEDIUM" if sev == "MODERATE" else sev
    if sev not in SEVERITY_ORDER:
        sev = _severity_from_score(score) if score is not None else "UNKNOWN"
    return Finding(
        id=cve_id,
        summary=summary.strip(),
        severity=sev,
        score=score,
        source=source,
        fixed_in=fixed_in,
        references=references[:5],
    )


async def scan_osv(client: httpx.AsyncClient, package: str, version: str) -> list[Finding]:
    """Fragar OSV.dev for ett PyPI-paket i en specifik version."""
    payload = {"package": {"name": package, "ecosystem": "PyPI"}, "version": version}
    try:
        r = await client.post(OSV_QUERY, json=payload, headers=_UA, timeout=45)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError:
        return []

    findings: list[Finding] = []
    seen: set[str] = set()
    for vuln in data.get("vulns", []):
        aliases = [a for a in vuln.get("aliases", []) if a.startswith("CVE")]
        cve_id = aliases[0] if aliases else vuln.get("id", "?")
        if cve_id in seen:
            continue
        seen.add(cve_id)

        severity = vuln.get("database_specific", {}).get("severity", "UNKNOWN")
        score = None
        for s in vuln.get("severity", []):
            if s.get("type", "").startswith("CVSS_V3"):
                score = _cvss3_base(s.get("score", ""))
                break
        if score is not None and severity in ("UNKNOWN", None):
            severity = _severity_from_score(score)

        fixed_in = _osv_fixed_version(vuln)
        refs = [ref.get("url", "") for ref in vuln.get("references", []) if ref.get("url")]
        findings.append(
            _finding(
                cve_id=cve_id,
                summary=vuln.get("summary") or vuln.get("details", "")[:200],
                severity=severity or "UNKNOWN",
                score=score,
                source="OSV",
                fixed_in=fixed_in,
                references=refs,
            )
        )
    return findings


def _cvss3_base(vector_or_score: str) -> float | None:
    """OSV ger ibland en ren poang, ibland en CVSS-vektor."""
    try:
        return float(vector_or_score)
    except (TypeError, ValueError):
        pass
    try:
        from cvss import CVSS3

        return float(CVSS3(vector_or_score).scores()[0])
    except Exception:  # noqa: BLE001
        return None


def _osv_fixed_version(vuln: dict) -> str | None:
    """Plockar ut den forsta 'fixed'-versionen ur OSV-postens ranges."""
    fixed: list[str] = []
    for affected in vuln.get("affected", []):
        for rng in affected.get("ranges", []):
            for event in rng.get("events", []):
                if "fixed" in event:
                    fixed.append(event["fixed"])
    return fixed[0] if fixed else None


def _cpe_version_affected(cpe_match: dict, version: str, target_cpe: str) -> bool:
    """Avgor om en NVD cpeMatch verkligen galler var version.

    NVD:s cpeName-sokning ar bred: den kan returnera CVE:er vars CPE saknar
    versionsgranser (rena jokertecken). Vi verifierar darfor sjalva att
    versionen ligger inom intervallet, sa att vi inte larmar falskt.
    """
    criteria = cpe_match.get("criteria", "")
    if not criteria.startswith(target_cpe):
        return False

    cur = parse_version(version)
    if cur is None:
        return False

    start_inc = parse_version(cpe_match.get("versionStartIncluding", ""))
    start_exc = parse_version(cpe_match.get("versionStartExcluding", ""))
    end_exc = parse_version(cpe_match.get("versionEndExcluding", ""))
    end_inc = parse_version(cpe_match.get("versionEndIncluding", ""))

    if any(v is not None for v in (start_inc, start_exc, end_exc, end_inc)):
        if start_inc is not None and cur < start_inc:
            return False
        if start_exc is not None and cur <= start_exc:
            return False
        if end_exc is not None and cur >= end_exc:
            return False
        if end_inc is not None and cur > end_inc:
            return False
        return True

    # Ingen grans: jamfor med exakt versionsangivelse i CPE-strangen.
    parts = criteria.split(":")
    cpe_ver = parts[5] if len(parts) > 5 else "*"
    if cpe_ver in ("*", "-", ""):
        return False  # obegransad - kan inte bekraftas
    exact = parse_version(cpe_ver)
    return exact is not None and exact == cur


async def scan_nvd(client: httpx.AsyncClient, product_key: str, version: str) -> list[Finding]:
    """Fragar NVD via CPE for en specifik produktversion.

    NVD utan API-nyckel tillater ca 5 anrop per 30 sekunder. Vid 403/429
    vantar vi och forsoker igen.
    """
    product = CPE_PRODUCTS.get(product_key)
    if not product:
        return []
    cpe = f"{product}:{version}:*:*:*:*:*:*:*"
    params = {"cpeName": cpe, "resultsPerPage": 200}

    data = None
    async with _NVD_LOCK:
        for attempt in range(4):
            try:
                r = await client.get(NVD_CVE, params=params, headers=_UA, timeout=60)
                if r.status_code in (403, 429):
                    await asyncio.sleep(7 * (attempt + 1))
                    continue
                r.raise_for_status()
                data = r.json()
                break
            except httpx.HTTPError:
                await asyncio.sleep(2 * (attempt + 1))
        # Hall oss under NVD:s grans mellan anrop (5 anrop / 30 s utan nyckel).
        await asyncio.sleep(2)
    if data is None:
        return []

    findings: list[Finding] = []
    for item in data.get("vulnerabilities", []):
        cve = item.get("cve", {})
        if not _nvd_cve_applies(cve, product, version):
            continue
        cve_id = cve.get("id", "?")
        desc = next((d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"), "")
        score, severity = _nvd_score(cve.get("metrics", {}))
        refs = [r.get("url", "") for r in cve.get("references", []) if r.get("url")]
        findings.append(
            _finding(
                cve_id=cve_id,
                summary=desc,
                severity=severity,
                score=score,
                source="NVD",
                fixed_in=None,
                references=refs,
            )
        )
    return findings


def _nvd_cve_applies(cve: dict, product: str, version: str) -> bool:
    """True om nagon av CVE:ns konfigurationer taecker var produkt+version."""
    for config in cve.get("configurations", []):
        for node in config.get("nodes", []):
            for match in node.get("cpeMatch", []):
                if match.get("vulnerable") and _cpe_version_affected(match, version, product):
                    return True
    return False


def _nvd_score(metrics: dict) -> tuple[float | None, str]:
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        if key in metrics and metrics[key]:
            data = metrics[key][0].get("cvssData", {})
            score = data.get("baseScore")
            severity = data.get("baseSeverity") or metrics[key][0].get("baseSeverity")
            if severity is None and score is not None:
                severity = _severity_from_score(score)
            return score, (severity or "UNKNOWN")
    return None, "UNKNOWN"


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Tar bort dubbletter (samma CVE fran OSV och NVD) och sorterar pa allvar."""
    by_id: dict[str, Finding] = {}
    for f in findings:
        existing = by_id.get(f["id"])
        if existing is None:
            by_id[f["id"]] = f
            continue
        # Forena: behall hogsta poang, men komplettera med fixed_in.
        if (f.get("score") or 0) > (existing.get("score") or 0):
            f["fixed_in"] = f.get("fixed_in") or existing.get("fixed_in")
            by_id[f["id"]] = f
        else:
            existing["fixed_in"] = existing.get("fixed_in") or f.get("fixed_in")
    out = list(by_id.values())
    out.sort(
        key=lambda f: (SEVERITY_ORDER.get(f.get("severity", "UNKNOWN"), 0), f.get("score") or 0),
        reverse=True,
    )
    return out


def severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    for f in findings:
        sev = f.get("severity", "UNKNOWN")
        sev = "MEDIUM" if sev == "MODERATE" else sev
        counts[sev if sev in counts else "UNKNOWN"] += 1
    return counts


async def scan_component(client: httpx.AsyncClient, component, version: str) -> list[Finding]:
    """Kor alla relevanta kall for en komponent och returnerar dedupade fynd."""
    if not version:
        return []
    cache_key = f"{component.key}:{version}"
    cached = scan_cache.get(cache_key)
    if cached is not None:
        return cached

    tasks = []
    if component.source == "pypi":
        tasks.append(scan_osv(client, component.package, version))
    if component.key in CPE_PRODUCTS:
        tasks.append(scan_nvd(client, component.key, version))
    if not tasks:
        return []
    results = await asyncio.gather(*tasks, return_exceptions=True)
    findings: list[Finding] = []
    for res in results:
        if isinstance(res, list):
            findings.extend(res)
    result = dedupe(findings)
    scan_cache.set(cache_key, result)
    return result
