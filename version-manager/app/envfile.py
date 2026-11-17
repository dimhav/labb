"""Laser och skriver .env-filen som styr stackens versioner."""
from __future__ import annotations

import re

from .config import ENV_FILE


_LINE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")


def read_env() -> dict[str, str]:
    """Returnerar alla nyckel=varde-par ur .env."""
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        m = _LINE.match(line.strip())
        if m:
            values[m.group("key")] = m.group("value")
    return values


def read_component_versions() -> dict[str, str]:
    """Returnerar nuvarande version per komponentnyckel."""
    from .config import COMPONENTS

    env = read_env()
    out: dict[str, str] = {}
    for c in COMPONENTS:
        raw = env.get(c.env_key, "")
        out[c.key] = image_tag(raw) if c.source == "docker" else raw
    return out


def image_tag(image: str) -> str:
    """Plockar ut taggen ur ett image-namn, t.ex. postgres:17.6 -> 17.6."""
    if not image:
        return ""
    if ":" in image.rsplit("/", 1)[-1]:
        return image.rsplit(":", 1)[1]
    return "latest"


def image_name(image: str) -> str:
    """Plockar ut image-namnet utan tagg."""
    if ":" in image.rsplit("/", 1)[-1]:
        return image.rsplit(":", 1)[0]
    return image


def update_env_version(env_key: str, value: str) -> None:
    """Skriver ett nytt varde for env_key. Bevarar ovriga rader och kommentarer."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    replaced = False
    for i, line in enumerate(lines):
        m = _LINE.match(line.strip())
        if m and m.group("key") == env_key:
            lines[i] = f"{env_key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{env_key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_env_value(component, target_version: str) -> str:
    """Bygger det varde som skall skrivas till .env for en komponent."""
    if component.source == "docker":
        name = image_name(read_env().get(component.env_key, component.package))
        return f"{name}:{target_version}"
    return target_version
