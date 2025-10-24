import os
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from .routes.directions import router as directions_router
from .routes.places import router as places_router

load_dotenv()


def _ensure_required_settings() -> None:
    google_maps_key = os.getenv("GOOGLE_MAPS_KEY", "").strip()
    if not google_maps_key:
        raise RuntimeError("GOOGLE_MAPS_KEY environment variable is required")


_ensure_required_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

app = FastAPI(title="HeyPico Maps Backend")
app.state.limiter = limiter


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware, limiter=limiter)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(places_router)
app.include_router(directions_router)


@app.get("/api/health")
@limiter.limit("60/minute")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


__all__ = ["app", "limiter"]