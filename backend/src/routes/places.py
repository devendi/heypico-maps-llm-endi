# backend/src/routes/places.py

from __future__ import annotations

from importlib import import_module, util
from typing import Any, Dict, List, Optional

from diskcache import Cache
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..services.maps_client import MapsAPIError, embed_url, text_search

# ===== Config & cache =====
CACHE_TTL_SECONDS = 600
CACHE_PATH = "./.cache"
cache = Cache(CACHE_PATH)

# ===== Models =====
class Place(BaseModel):
    name: str
    address: str
    lat: float
    lng: float
    place_id: str
    rating: Optional[float] = None


class PlacesResponse(BaseModel):
    query: str
    places: List[Place]
    embedUrl: Optional[str] = None
    directionsUrl: Optional[str] = None


# ===== Limiter loader (avoid hard import cycle) =====
def _load_limiter() -> Limiter:
    limiter_instance: Optional[Limiter] = None
    main_spec = util.find_spec("..main", package=__package__)
    if main_spec is not None:
        module = import_module("..main", package=__package__)
        maybe_limiter = getattr(module, "limiter", None)
        if isinstance(maybe_limiter, Limiter):
            limiter_instance = maybe_limiter
    if limiter_instance is None:
        limiter_instance = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    return limiter_instance


limiter = _load_limiter()

# ===== Router =====
router = APIRouter(prefix="/api", tags=["places"])


def _cache_key(query: str, lat: Optional[float], lng: Optional[float]) -> str:
    lat_part = "" if lat is None else f"{lat:.6f}"
    lng_part = "" if lng is None else f"{lng:.6f}"
    return f"places|{query.strip()}|{lat_part}|{lng_part}"


@router.get("/places", response_model=PlacesResponse)
@limiter.limit("60/minute")
async def get_places(
    request: Request,
    query: str = Query(..., min_length=2, description="Search query"),
    lat: Optional[float] = Query(None, description="Latitude of the search origin"),
    lng: Optional[float] = Query(None, description="Longitude of the search origin"),
) -> PlacesResponse:
    key = _cache_key(query, lat, lng)
    cached = cache.get(key)
    if cached:
        # cached is dict produced by model_dump()
        return PlacesResponse(**cached)

    try:
        # text_search returns dict {"query": str, "places": [ {name, address, lat, lng, place_id, rating?}, ... ]}
        result = await text_search(query.strip(), lat=lat, lng=lng)
    except MapsAPIError as e:
        raise HTTPException(status_code=502, detail=f"maps_api_error: {e}") from e
    except Exception:
        raise HTTPException(status_code=500, detail="internal_error")

    if isinstance(result, dict):
        items: List[Dict[str, Any]] = [p for p in result.get("places", []) if isinstance(p, dict)]
    elif isinstance(result, list):
        # fallback shape if client returns list directly
        items = [p for p in result if isinstance(p, dict)]
    else:
        items = []

    top = items[:3]
    places_models = [Place(**p) for p in top]

    embed_value: Optional[str] = None
    directions_value: Optional[str] = None
    if places_models:
        first = places_models[0]
        embed_value = embed_url(first.lat, first.lng, q=first.name)
        if lat is not None and lng is not None:
            directions_value = (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={lat},{lng}"
                f"&destination={first.lat},{first.lng}"
            )

    response = PlacesResponse(
        query=query.strip(),
        places=places_models,
        embedUrl=embed_value,
        directionsUrl=directions_value,
    )

    # store as plain dict for cache
    cache.set(key, response.model_dump(), expire=CACHE_TTL_SECONDS)
    return response
