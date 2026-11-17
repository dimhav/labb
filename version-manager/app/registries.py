"""Uppslagning av tillgangliga versioner hos Docker Hub och PyPI."""
from __future__ import annotations

import asyncio
import re

import httpx
from packaging.version import InvalidVersion, Version


DOCKER_HUB = "https://hub.docker.com/v2"
PYPI = "https://pypi.org/pypi"
_UA = {"User-Agent": "pgsqlmesh-version-manager/1.0"}

_SEMVER = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")


class RegistryError(RuntimeError):
    """Fel vid kontakt med en registry."""


async def _get_json(
    client: httpx.AsyncClient, url: str, *, params: dict | None = None, timeout: int = 12, attempts: int = 3
) -> dict:
    """GET med enkla omforsok - natverket ar ibland tillfalligt trogt."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            r = await client.get(url, params=params, headers=_UA, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            last = exc
            await asyncio.sleep(1.0 * (i + 1))
    raise RegistryError(f"Kunde inte hamta {url}: {last}")


def parse_version(value: str) -> Version | None:
    try:
        return Version(value)
    except InvalidVersion:
        return None


async def docker_tags(
    client: httpx.AsyncClient, image: str, *, pages: int = 3, name: str | None = None
) -> list[dict]:
    """Hamtar taggar for ett image fran Docker Hub.

    name : filtrerar pa taggnamn (Docker Hubs server-side sokning), t.ex. "5.".
    """
    owner, _, repo = image.partition("/")
    if not repo:
        owner, repo = "library", owner
    tags: list[dict] = []
    url = f"{DOCKER_HUB}/repositories/{owner}/{repo}/tags"
    params: dict = {"page_size": 100, "ordering": "last_updated"}
    if name:
        params["name"] = name
    for _ in range(pages):
        data = await _get_json(client, url, params=params)
        tags.extend(data.get("results", []))
        if not data.get("next"):
            break
        url = data["next"]
        params = None
    return tags


async def latest_docker_version(
    client: httpx.AsyncClient,
    image: str,
    *,
    prefix: str | None = None,
    major: int | None = None,
) -> tuple[str | None, str | None]:
    """Returnerar (senaste stabila version, releasedatum) for ett image.

    prefix  : kraver att taggen borjar med denna strang (t.ex. "5.")
    major   : begransar till en specifik major-version
    Taggar med suffix (rc, -dev, -py311 ...) hoppas over - endast rena
    versionsnummer (X.Y eller X.Y.Z) raknas som stabila.
    """
    name_filter = f"{major}." if major is not None else prefix
    tags = await docker_tags(client, image, name=name_filter)
    best: tuple[Version, str] | None = None
    for tag in tags:
        name = tag.get("name", "")
        if prefix and not name.startswith(prefix):
            continue
        m = _SEMVER.match(name)
        if not m:
            continue
        if major is not None and int(m.group(1)) != major:
            continue
        v = parse_version(name)
        if v is None:
            continue
        if best is None or v > best[0]:
            best = (v, tag.get("last_updated", "")[:10])
    if best is None:
        return None, None
    return str(best[0]), best[1]


async def docker_tag_exists(client: httpx.AsyncClient, image: str, tag: str) -> bool:
    """Kontrollerar om en specifik tagg finns pa Docker Hub."""
    owner, _, repo = image.partition("/")
    if not repo:
        owner, repo = "library", owner
    url = f"{DOCKER_HUB}/repositories/{owner}/{repo}/tags/{tag}"
    try:
        r = await client.get(url, headers=_UA, timeout=20)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def latest_pypi_version(client: httpx.AsyncClient, package: str) -> tuple[str | None, str | None]:
    """Returnerar (senaste version, releasedatum) for ett PyPI-paket."""
    data = await _get_json(client, f"{PYPI}/{package}/json")
    version = data.get("info", {}).get("version")
    released = None
    files = data.get("releases", {}).get(version or "", [])
    if files:
        released = files[0].get("upload_time", "")[:10]
    return version, released


async def pypi_release_dates(client: httpx.AsyncClient, package: str) -> dict[str, str]:
    """Returnerar {version: releasedatum} for ett paket."""
    r = await client.get(f"{PYPI}/{package}/json", headers=_UA, timeout=30)
    r.raise_for_status()
    data = r.json()
    out: dict[str, str] = {}
    for version, files in data.get("releases", {}).items():
        if files:
            out[version] = files[0].get("upload_time", "")[:10]
    return out


async def resolve_latest(client: httpx.AsyncClient, component) -> tuple[str | None, str | None]:
    """Hamtar senaste version for en komponent utifran dess kanal."""
    channel = component.channel or {}
    kind = channel.get("kind")

    if kind == "pypi":
        return await latest_pypi_version(client, component.package)

    if kind == "pypi_docker":
        # Versionen kommer fran PyPI (auktoritativ), men maste finnas som
        # Docker-tagg. Faller tillbaka pa hogsta tillgangliga Docker-tagg.
        image = channel.get("image", component.package)
        try:
            version, released = await latest_pypi_version(client, channel["pypi"])
            if version and await docker_tag_exists(client, image, version):
                return version, released
        except RegistryError:
            pass
        return await latest_docker_version(client, image, prefix=channel.get("prefix"))

    return await latest_docker_version(
        client,
        channel.get("image", component.package),
        prefix=channel.get("prefix"),
        major=channel.get("major"),
    )
