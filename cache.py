import hashlib
import json
import time
from typing import Optional, Dict, Any

_cache_store: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 3600

def build_cache_key(proposed_medicines: list[str], current_medications: list[str]) -> str:
    sorted_proposed = sorted([m.strip().lower() for m in proposed_medicines])
    sorted_current = sorted([m.strip().lower() for m in current_medications])

    key_data = {
        "proposed": sorted_proposed,
        "current": sorted_current
    }

    key_string = json.dumps(key_data, sort_keys=True)
    return hashlib.sha256(key_string.encode('utf-8')).hexdigest()

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
        "expires_at": time.time() + CACHE_TTL_SECONDS
    }

def get_cache_stats() -> Dict[str, int]:
    now = time.time()
    active = sum(1 for v in _cache_store.values() if v["expires_at"] > now)
    return {"total_entries": len(_cache_store), "active_entries": active}