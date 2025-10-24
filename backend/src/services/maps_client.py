import os
from urllib.parse import quote_plus

import httpx


class MapsAPIError(Exception):
    """Raised when the Google Maps API returns an error response."""


def _get_api_key() -> str:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        api_key = os.environ.get("GOOGLE_MAPS_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY environment variable is not set")
    return api_key


async def text_search(
    query: str,
    lat: float | None = None,
    lng: float | None = None,
    radius_m: int | None = None,
) -> dict:
    if (lat is None) != (lng is None):
        raise ValueError("Both lat and lng must be provided together")

    params: dict[str, str] = {
        "query": query,
        "key": _get_api_key(),
        "language": "id",
        "region": "ID",
    }
    if lat is not None and lng is not None:
        params["location"] = f"{lat},{lng}"
        if radius_m:
            params["radius"] = str(radius_m)
        else:
            params["radius"] = "5000"

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params=params,
        )
        response.raise_for_status()
        payload = response.json()

    status = payload.get("status")
    if status != "OK":
        error_message = payload.get("error_message")
        details = f" ({error_message})" if error_message else ""
        raise MapsAPIError(f"Text search failed with status {status}{details}")

    places: list[dict[str, object]] = []
    for result in payload.get("results", []):
        geometry = result.get("geometry", {})
        location = geometry.get("location", {})
        places.append(
            {
                "name": result.get("name", ""),
                "address": result.get("formatted_address", ""),
                "lat": float(location.get("lat")) if location.get("lat") is not None else None,
                "lng": float(location.get("lng")) if location.get("lng") is not None else None,
                "place_id": result.get("place_id", ""),
                "rating": result.get("rating"),
            }
        )

    return {"query": query, "places": places}


async def directions(origin: str, dest: str) -> dict:
    params = {
        "origin": origin,
        "destination": dest,
        "key": _get_api_key(),
        "language": "id",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params=params,
        )
        response.raise_for_status()
        payload = response.json()

    status = payload.get("status")
    if status != "OK":
        error_message = payload.get("error_message")
        details = f" ({error_message})" if error_message else ""
        raise MapsAPIError(f"Directions request failed with status {status}{details}")

    directions_url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote_plus(origin)}&destination={quote_plus(dest)}"
    )

    return {
        "origin": origin,
        "destination": dest,
        "directionsUrl": directions_url,
    }


def embed_url(lat: float, lng: float, q: str) -> str:
    """Return an embeddable map URL without exposing the API key."""
    encoded_query = quote_plus(q)
    # Format the query using the ``loc:`` prefix so that the iframe zooms to the
    # exact coordinates while still displaying the place name. This variant uses
    # the public maps embed endpoint, which works without an API key and avoids
    # triggering "invalid key" errors in the demo frontend.
    return (
        "https://maps.google.com/maps?"
        f"q={encoded_query}+loc:{lat},{lng}&hl=id&z=15&output=embed"
    )