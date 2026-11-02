"""Read-only identity search against an explicitly staged SmartQuote V10 catalogue.

The catalogue must be provisioned privately by IT, outside GitHub. This module
does not supply rates, claim commercial approval or auto-resolve ambiguous SKUs.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from .pilot_access import actor

router = APIRouter(prefix="/api/quoting", tags=["SmartQuote equipment identity"])
ENV_NAME = "PULSE_SMARTQUOTE_CATALOG_JSON"
MAX_FILE_BYTES = 20 * 1024 * 1024


def catalogue_file():
    value = os.environ.get(ENV_NAME, "").strip()
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".json":
        return None
    return path


@lru_cache(maxsize=2)
def _catalogue(path: str, modified_ns: int, size: int):
    """Cache only source-derived identity attributes, never customer data."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(503, "SmartQuote catalogue cannot be decoded.") from exc
    if not isinstance(raw, list) or len(raw) > 30000:
        raise HTTPException(503, "SmartQuote catalogue has an unexpected format.")
    products = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sku = str(item.get("sku") or "").strip().upper()[:100]
        if not sku:
            continue
        products.append({
            "sku": sku,
            "name": str(item.get("name") or "")[:250],
            "model": str(item.get("model") or "")[:120],
            "group": str(item.get("group") or "")[:120],
        })
    counts = Counter(p["sku"] for p in products)
    return products, counts


def _load():
    path = catalogue_file()
    if path is None:
        raise HTTPException(503, "Approved SmartQuote catalogue not configured.")
    try:
        stat = path.stat()
    except OSError as exc:
        raise HTTPException(503, "Catalogue file unavailable.") from exc
    if stat.st_size > MAX_FILE_BYTES:
        raise HTTPException(503, "Catalogue exceeds pilot read-only limit.")
    return _catalogue(str(path), stat.st_mtime_ns, stat.st_size)


@router.get("/catalogue/search")
def search_catalogue(q: str = Query(..., min_length=2, max_length=100),
                     limit: int = Query(15, ge=1, le=50)):
    actor()
    phrase = q.strip().casefold()
    if len(phrase) < 2:
        raise HTTPException(422, "Search by at least two characters.")
    products, counts = _load()
    matches = []
    for p in products:
        code = p["sku"].casefold()
        model = p["model"].casefold()
        name = p["name"].casefold()
        if code == phrase:
            score = 1000
        elif code.startswith(phrase):
            score = 800
        elif model == phrase:
            score = 700
        elif phrase in code or phrase in model:
            score = 400
        elif phrase in name:
            score = 200
        else:
            continue
        matches.append((score, p))
    matches.sort(key=lambda item: (-item[0], item[1]["sku"]))
    return {
        "results": [
            {**p, "duplicate_sku": counts[p["sku"]] > 1,
             "pricing_approved": False, "source": "SmartQuote identity catalogue"}
            for _, p in matches[:limit]
        ],
        "total": len(matches), "identity_only": True, "price_supplied": False,
    }
