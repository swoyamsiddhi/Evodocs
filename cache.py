import hashlib
import json
import os
import time
from typing import Optional, Dict, Any

_cache_store: Dict[str, Dict[str, Any]] = {}

CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

def build_cache_key(
    proposed_medicines: list[str],
    current_medications: list[str],
    known_allergies: list[str] = None,
    conditions: list[str] = None,
) -> str:
    key_data = {
        "proposed":    sorted([m.strip().lower() for m in proposed_medicines]),
        "current":     sorted([m.strip().lower() for m in (current_medications or [])]),
        "allergies":   sorted([a.strip().lower() for a in (known_allergies or [])]),
        "conditions":  sorted([c.strip().lower() for c in (conditions or [])]),
    }
    key_string = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(key_string.encode("utf-8")).hexdigest()

def get_cached(key: str) -> Optional[Dict[str, Any]]:
    entry = _cache_store.get(key)
    if entry is None:
        return None
    if time.time() > entry["expires_at"]:
        del _cache_store[key]
        return None
    return entry["data"]

def set_cached(key: str, data: Dict[str, Any]) -> None:
    _cache_store[key] = {
        "data": data,
        "expires_at": time.time() + CACHE_TTL_SECONDS,
    }

def get_cache_stats() -> Dict[str, int]:
    now = time.time()
    active = sum(1 for v in _cache_store.values() if v["expires_at"] > now)
    return {"total_entries": len(_cache_store), "active_entries": active}