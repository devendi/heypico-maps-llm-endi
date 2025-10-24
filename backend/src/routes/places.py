from __future__ import annotations

from importlib import import_module, util
from typing import Any, Dict, List, Optional

from diskcache import Cache
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..services.maps_client import MapsAPIError, embed_url, text_search

CACHE_TTL_SECONDS = 600
CACHE_PATH = "./.cache"

cache = Cache(CACHE_PATH)


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

router = APIRouter(prefix="/api", tags=["places"])


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_place(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    location: Dict[str, Any] = {}
    if "lat" in raw and "lng" in raw:
        location = {"lat": raw.get("lat"), "lng": raw.get("lng")}
    elif "location" in raw:
        location = raw.get("location") or {}
    else:
        geometry = raw.get("geometry") or {}
        location = geometry.get("location") or {}

    lat_value = _float_or_none(location.get("lat"))
    lng_value = _float_or_none(location.get("lng"))
    if lat_value is None or lng_value is None:
        return None

    rating_value = _float_or_none(raw.get("rating"))

    address_value = raw.get("formatted_address") or raw.get("address") or ""

    place_id_value = raw.get("place_id") or raw.get("id")
    if not place_id_value:
        return None

    name_value = raw.get("name")
    if not name_value:
        return None

    return {
        "name": name_value,
        "address": address_value,
        "lat": lat_value,
        "lng": lng_value,
        "place_id": place_id_value,
        "rating": rating_value,
    }


def _cache_key(query: str, lat: Optional[float], lng: Optional[float]) -> str:
    lat_part = "" if lat is None else f"{lat:.6f}"
    lng_part = "" if lng is None else f"{lng:.6f}"
    return f"{query}|{lat_part}|{lng_part}"


@router.get("/places", response_model=PlacesResponse)
@limiter.limit("60/minute")
async def get_places(
    request: Request,
    query: str = Query(..., min_length=2, description="Search query"),
    lat: Optional[float] = Query(None, description="Latitude of the search origin"),
    lng: Optional[float] = Query(None, description="Longitude of the search origin"),
) -> PlacesResponse:
    cache_key = _cache_key(query, lat, lng)
    cached_places = cache.get(cache_key)

    places_data: List[Dict[str, Any]]
    if cached_places is not None:
        places_data = cached_places
    else:
        try:
            raw_places = text_search(query, lat=lat, lng=lng)
        except MapsAPIError as exc:  # pragma: no cover - depends on external API
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive programming
            raise HTTPException(status_code=500, detail="internal_error") from exc

        normalized_places: List[Dict[str, Any]] = []
        if isinstance(raw_places, list):
            for item in raw_places:
                if not isinstance(item, dict):
                    continue
                normalized = _normalize_place(item)
                if normalized is not None:
                    normalized_places.append(normalized)
        places_data = normalized_places
        cache.set(cache_key, places_data, expire=CACHE_TTL_SECONDS)

    places_models = [Place(**place) for place in places_data]

    embed_value: Optional[str] = None
    directions_value: Optional[str] = None

    if places_models:
        first_place = places_models[0]
        embed_value = embed_url(first_place.lat, first_place.lng, q=first_place.name)

        if lat is not None and lng is not None:
            directions_value = (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={lat},{lng}"
                f"&destination={first_place.lat},{first_place.lng}"
            )

    return PlacesResponse(
        query=query,
        places=places_models,
        embedUrl=embed_value,
        directionsUrl=directions_value,
    )