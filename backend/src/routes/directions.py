from __future__ import annotations

import re
from typing import Tuple
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..services.maps_client import directions as maps_directions, MapsAPIError


router = APIRouter(prefix="/api", tags=["directions"])
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

_COORDINATE_PATTERN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class DirectionsResponse(BaseModel):
    origin: str
    destination: str
    directionsUrl: str


def _parse_coordinate(value: str) -> Tuple[float, float, str, str]:
    match = _COORDINATE_PATTERN.match(value)
    if not match:
        raise ValueError("invalid_format")

    lat_str = match.group(1)
    lng_str = match.group(2)

    lat = float(lat_str)
    lng = float(lng_str)

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("out_of_range")

    return lat, lng, lat_str, lng_str


@router.get("/directions", response_model=DirectionsResponse)
@limiter.limit("60/minute")
async def get_directions(
    request: Request,
    origin: str = Query(..., description="Latitude and longitude in 'lat,lng' format"),
    dest: str = Query(..., description="Latitude and longitude in 'lat,lng' format"),
) -> DirectionsResponse:
    try:
        origin_lat, origin_lng, origin_lat_str, origin_lng_str = _parse_coordinate(origin)
        dest_lat, dest_lng, dest_lat_str, dest_lng_str = _parse_coordinate(dest)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_coordinates")

    origin_normalized = f"{origin_lat_str},{origin_lng_str}"
    dest_normalized = f"{dest_lat_str},{dest_lng_str}"

    try:
        maps_directions(origin=origin_normalized, destination=dest_normalized)
    except MapsAPIError as exc:  # pragma: no cover - depends on external service
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="internal_error") from exc

    params = {
        "api": "1",
        "origin": origin_normalized,
        "destination": dest_normalized,
    }
    url = f"https://www.google.com/maps/dir/?{urlencode(params)}"

    return DirectionsResponse(
        origin=origin_normalized,
        destination=dest_normalized,
        directionsUrl=url,
    )