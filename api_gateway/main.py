"""
API Gateway — FastAPI application.
Proxies AI recommendation endpoints to ai_service.

Routes:
  - POST /api/v1/trips/recommend     — Generate heritage travel itinerary
  - POST /api/v1/recommend           — Alias for /trips/recommend
  - POST /api/v1/routes/plan         — Plan a fixed start/end route
  - GET  /api/v1/health              — Health check
  - GET  /                           — Gateway health & docs
"""

import logging
import time
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx

from config import settings
from config.logging_config import setup_logging

setup_logging(level=settings.log_level, log_dir=settings.log_dir, log_file=settings.log_file)
log = logging.getLogger("heritage.gateway")

app = FastAPI(
    title="Vietnam Heritage Travel AI Service Gateway",
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])
    t0 = time.time()
    response = await call_next(request)
    ms = int((time.time() - t0) * 1000)
    log.info("%s %s → %s  %dms  [%s]",
             request.method, request.url.path, response.status_code, ms, req_id)
    response.headers["X-Request-ID"] = req_id
    return response


@app.get("/")
async def root():
    return {"message": "Vietnam Heritage Travel AI Gateway", "docs": "/docs"}


@app.get("/api/v1/health")
async def health():
    ai_healthy = False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ai_service_url}/health")
            ai_healthy = resp.status_code == 200
    except Exception:
        pass

    return {
        "gateway": "ok",
        "ai_service": "ok" if ai_healthy else "unreachable",
        "version": settings.version,
    }


@app.post("/api/v1/recommend")
async def recommend_alias(payload: dict):
    """Alias for /api/v1/trips/recommend to support legacy clients."""
    return await _proxy_post("/api/v1/recommend", payload)


@app.post("/api/v1/trips/recommend")
async def recommend_trip(payload: dict):
    """Forward trip recommendation request to AI service."""
    return await _proxy_post("/api/v1/recommend", payload)


@app.post("/api/v1/routes/plan")
async def route_plan(payload: dict):
    """Forward fixed start/end route planning request to AI service."""
    return await _proxy_post("/api/v1/routes/plan", payload)


@app.get("/api/v1/heritage-sites")
async def list_heritage_sites():
    return await _proxy_get("/api/v1/heritage-sites")


@app.get("/api/v1/heritage-sites/{path:path}")
async def heritage_site_detail(path: str):
    return await _proxy_get(f"/api/v1/heritage-sites/{path}")


@app.get("/api/v1/images/stats")
async def image_stats():
    return await _proxy_get("/api/v1/images/stats")


async def _proxy_post(path: str, payload: dict):
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{settings.ai_service_url}{path}", json=payload)
            ms = int((time.time() - t0) * 1000)
            if resp.status_code >= 400:
                log.warning("upstream %s → %s  %dms  detail=%s",
                            path, resp.status_code, ms, _error_body(resp)[:300])
            else:
                log.debug("upstream %s → %s  %dms", path, resp.status_code, ms)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        body = _error_body(e.response)
        log.error("upstream error %s → %s: %s", path, e.response.status_code, body[:300])
        raise HTTPException(status_code=e.response.status_code, detail=body)
    except httpx.RequestError as e:
        log.error("upstream %s → UNREACHABLE: %s", path, str(e))
        raise HTTPException(status_code=503, detail=f"AI service unavailable")


async def _proxy_get(path: str):
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{settings.ai_service_url}{path}")
            ms = int((time.time() - t0) * 1000)
            if resp.status_code >= 400:
                log.warning("upstream %s → %s  %dms", path, resp.status_code, ms)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        log.error("upstream error %s → %s", path, e.response.status_code)
        raise HTTPException(status_code=e.response.status_code, detail=_error_body(e.response))
    except httpx.RequestError as e:
        log.error("upstream %s → UNREACHABLE", path)
        raise HTTPException(status_code=503, detail=f"AI service unavailable")


def _error_body(response) -> str:
    try:
        return response.json().get("detail", response.text)
    except Exception:
        return response.text or "Unknown error"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
