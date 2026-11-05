"""Shared helpers: paths, a polite cached HTTP client for the GBIF API."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
CACHE = DATA / "cache"
for _p in (RAW, INTERIM, PROCESSED, CACHE):
    _p.mkdir(parents=True, exist_ok=True)

GBIF = "https://api.gbif.org/v1"

# South Asian countries/regions as they appear in Dr. Duke's ETHNOBOT "COUNTRY" field
SOUTH_ASIA_PREFIXES = (
    "India", "Nepal", "Pakistan", "Bangladesh", "Sri Lanka", "Ceylon",
    "Bhutan", "Sikkim", "Himalaya", "Kashmir", "Assam",
)

_session = requests.Session()
_session.headers["User-Agent"] = "EthnoHack2026-medicinal-plant-risk/0.1 (research prototype)"


def get_json(url: str, params: dict | None = None, cache: bool = True, retries: int = 9):
    """GET a JSON resource with on-disk caching (makes the pipeline resumable & reproducible)."""
    key = hashlib.sha1((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()
    path = CACHE / key[:2] / f"{key}.json"
    if cache and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    delay = 1.0
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=60)
            if r.status_code == 404:
                data = None
            elif r.status_code in (429, 500, 502, 503, 504):
                ra = r.headers.get("Retry-After")
                if ra and ra.isdigit():
                    time.sleep(min(int(ra), 120))
                raise requests.HTTPError(f"status {r.status_code}")
            else:
                r.raise_for_status()
                data = r.json()
            if cache:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 60)
