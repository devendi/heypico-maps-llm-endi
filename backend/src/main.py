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

from src.routes.directions import router as directions_router
from src.routes.llm_places import router as llm_places_router
from src.routes.places import router as places_router
from src.services.llm_service import ensure_model_loaded

load_dotenv()


def _ensure_required_settings() -> None:
    google_maps_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not google_maps_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY environment variable is required")


_ensure_required_settings()

rate_limit_value = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30") or "30")

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{rate_limit_value}/minute"])

app = FastAPI(title="HeyPico Maps Backend")
app.state.limiter = limiter


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(places_router)
app.include_router(llm_places_router)
app.include_router(directions_router)

@app.get("/api/health")
@limiter.limit(f"{rate_limit_value}/minute")
async def health(request: Request) -> Dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
async def _warmup_model() -> None:  # pragma: no cover - side effect only
    ensure_model_loaded()
    
__all__ = ["app", "limiter"]