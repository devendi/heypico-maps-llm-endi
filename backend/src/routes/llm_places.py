"""LLM assisted place search endpoint."""
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
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
USER_SEARCH_RADIUS_METERS = int(os.getenv("USER_SEARCH_RADIUS_METERS", "3000") or "3000")
cache = Cache(CACHE_PATH)

# ==== Limiter: JANGAN impor dari main.py (hindari circular import) ====
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{RATE_LIMIT}/minute"])

# ==== Models ====
class LLMPlacesRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    user_lat: Optional[float] = Field(default=None)
    user_lng: Optional[float] = Field(default=None)

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

def _cache_key(
    intent: Dict[str, Any],
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
) -> str:
    def _format_coord(value: Optional[float]) -> str:
        if value is None:
            return ""
        try:
            return f"{float(value):.6f}"
        except (TypeError, ValueError):
            return ""
    return "|".join([
        intent.get("query", "").strip().lower(),
        intent.get("location", "").strip().lower(),
        str(intent.get("radius_m", "")),
        _format_coord(user_lat),
        _format_coord(user_lng),
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

def _build_directions_url(
    intent: Dict[str, Any],
    place: Dict[str, Any],
    user_coords: Optional[Tuple[float, float]] = None,
) -> Optional[str]:
    destination = None
    if place.get("lat") is not None and place.get("lng") is not None:
        destination = f"{place['lat']},{place['lng']}"
    elif place.get("place_id"):
        destination = f"place_id:{place['place_id']}"
    elif place.get("name"):
        destination = place["name"]
    if not destination:
        return None
    origin = ""
    if user_coords and user_coords[0] is not None and user_coords[1] is not None:
        origin = f"{user_coords[0]},{user_coords[1]}"
    else:
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
    user_lat: Optional[float] = None
    user_lng: Optional[float] = None

    if payload.user_lat is not None and payload.user_lng is not None:
        try:
            user_lat = float(payload.user_lat)
            user_lng = float(payload.user_lng)
        except (TypeError, ValueError):
            logger.warning("Invalid user coordinates provided: lat=%s lng=%s", payload.user_lat, payload.user_lng)
            user_lat = None
            user_lng = None

    key = _cache_key(intent, user_lat=user_lat, user_lng=user_lng)

    cached = cache.get(key)
    if cached:
        return LLMPlacesResponse(**cached)

    intent_query = str(intent.get("query") or "").strip()
    intent_location = str(intent.get("location") or "").strip()
    if user_lat is not None and user_lng is not None:
        # When we have the user's coordinates, rely on them for proximity instead
        # of forcing the textual query to include an explicit location. This avoids
        # mixing prompts like "near Senopati" with the actual user location which
        # can lead to confusing or incorrect results around the wrong area.
        search_query = intent_query or intent_location or payload.prompt.strip()
    else:
        if intent_query and intent_location:
            search_query = f"{intent_query} near {intent_location}"
        else:
            search_query = intent_query or intent_location or payload.prompt.strip()

    try:
        if user_lat is not None and user_lng is not None:
            radius_candidate = intent.get("radius_m")
            radius_value = USER_SEARCH_RADIUS_METERS
            if radius_candidate is not None:
                try:
                    candidate_int = int(radius_candidate)
                except (TypeError, ValueError):
                    candidate_int = None
                if candidate_int and candidate_int > 0:
                    radius_value = candidate_int

            maps_response = await text_search(
                search_query,
                lat=user_lat,
                lng=user_lng,
                radius_m=radius_value,
            )
        else:
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
    user_origin: Optional[Tuple[float, float]] = None
    if user_lat is not None and user_lng is not None:
        user_origin = (user_lat, user_lng)

    directions = _build_directions_url(intent, places[0], user_origin) if places else None

    response = LLMPlacesResponse(
        intent=IntentResponse(**intent),
        places=[PlaceItem(**place) for place in places[:5]],
        embed_url=embed,
        directions_url=directions,
    )

    cache.set(key, response.model_dump(), expire=CACHE_TTL_SECONDS)
    return response

__all__ = ["router"]
