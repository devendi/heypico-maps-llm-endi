"""LLM assisted place search endpoint."""
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from diskcache import Cache
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..services.llm_service import extract_intent_from_prompt
from ..services.maps_client import MapsAPIError, embed_url as build_embed_url, text_search

logger = logging.getLogger(__name__)

# ==== Config & cache ====
CACHE_PATH = "./.cache"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600") or "600")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30") or "30")
cache = Cache(CACHE_PATH)

# ==== Limiter: JANGAN impor dari main.py (hindari circular import) ====
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT}/minute"])

# ==== Models ====
class LLMPlacesRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)

class PlaceItem(BaseModel):
    name: str
    address: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    place_id: str
    maps_url: str

class IntentResponse(BaseModel):
    query: str
    location: str
    radius_m: int

class LLMPlacesResponse(BaseModel):
    intent: IntentResponse
    places: List[PlaceItem]
    embed_url: str
    directions_url: Optional[str]

# Pydantic v2 schema build
LLMPlacesRequest.model_rebuild()
PlaceItem.model_rebuild()
IntentResponse.model_rebuild()
LLMPlacesResponse.model_rebuild()

# ==== Router ====
router = APIRouter(prefix="/api/llm", tags=["llm-places"])

def _cache_key(intent: Dict[str, Any]) -> str:
    return "|".join([
        intent.get("query", "").strip().lower(),
        intent.get("location", "").strip().lower(),
        str(intent.get("radius_m", "")),
    ])

def _build_embed_url(intent: Dict[str, Any], place: Optional[Dict[str, Any]]) -> str:
    search = f"{intent['query']} near {intent['location']}".strip()

    if place:
        lat = place.get("lat")
        lng = place.get("lng")
        name = place.get("name") or intent.get("query") or search or ""

        if lat is not None and lng is not None:
            try:
                return build_embed_url(float(lat), float(lng), q=str(name))
            except (TypeError, ValueError):
                # Fallback to the search URL below if coordinates are malformed
                pass

    if not search:
        return "https://www.google.com/maps"

    return "https://maps.google.com/maps?output=embed&q=" + quote_plus(search)

def _build_directions_url(intent: Dict[str, Any], place: Dict[str, Any]) -> Optional[str]:
    destination = None
    if place.get("lat") is not None and place.get("lng") is not None:
        destination = f"{place['lat']},{place['lng']}"
    elif place.get("place_id"):
        destination = f"place_id:{place['place_id']}"
    elif place.get("name"):
        destination = place["name"]
    if not destination:
        return None
    origin = intent.get("location") or ""
    params = ["https://www.google.com/maps/dir/?api=1"]
    if origin:
        params.append(f"origin={quote_plus(origin)}")
    params.append(f"destination={quote_plus(destination)}")
    return "&".join(params)

def _maps_url(place_id: str) -> str:
    if not place_id:
        return "https://www.google.com/maps"
    return f"https://www.google.com/maps/place/?q=place_id:{quote_plus(place_id)}"

@router.post("/places", response_model=LLMPlacesResponse)
@limiter.limit(f"{RATE_LIMIT}/minute")
async def llm_places_endpoint(
    request: Request,
    payload: LLMPlacesRequest,
) -> LLMPlacesResponse:
    intent = extract_intent_from_prompt(payload.prompt)
    key = _cache_key(intent)

    cached = cache.get(key)
    if cached:
        return LLMPlacesResponse(**cached)

    search_query = f"{intent['query']} near {intent['location']}".strip()

    try:
        maps_response = await text_search(search_query, radius_m=intent.get("radius_m"))
    except MapsAPIError as exc:
        logger.exception("Maps API error: %s", exc)
        raise HTTPException(status_code=502, detail="maps_api_error") from exc
    except Exception as exc:
        logger.exception("Unexpected error calling Maps API: %s", exc)
        raise HTTPException(status_code=500, detail="internal_error") from exc

    places_payload = maps_response.get("places") if isinstance(maps_response, dict) else []
    places: List[Dict[str, Any]] = []
    for item in places_payload or []:
        if not isinstance(item, dict):
            continue
        place_id = str(item.get("place_id", ""))
        places.append({
            "name": item.get("name", ""),
            "address": item.get("address", ""),
            "lat": item.get("lat"),
            "lng": item.get("lng"),
            "place_id": place_id,
            "maps_url": _maps_url(place_id),
        })

    first_place = places[0] if places else None
    embed = _build_embed_url(intent, first_place)
    directions = _build_directions_url(intent, places[0]) if places else None

    response = LLMPlacesResponse(
        intent=IntentResponse(**intent),
        places=[PlaceItem(**place) for place in places[:5]],
        embed_url=embed,
        directions_url=directions,
    )

    cache.set(key, response.model_dump(), expire=CACHE_TTL_SECONDS)
    return response

__all__ = ["router"]
