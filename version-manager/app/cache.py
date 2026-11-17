"""Enkel in-memory-cache med TTL.

Anvands for att slippa skanna om samma version vid varje klick. Resultaten
fran OSV/NVD och registryn andras langsamt, sa en TTL pa nagra minuter racker.
"""
from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: int = 900) -> None:
        self.ttl = ttl_seconds
        self._data: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if time.time() > expires:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._data[key] = (time.time() + self.ttl, value)

    def clear(self) -> None:
        self._data.clear()


# Scannade CVE-resultat per (komponent, version).
scan_cache = TTLCache(ttl_seconds=900)
# Senaste version per komponent.
version_cache = TTLCache(ttl_seconds=900)
