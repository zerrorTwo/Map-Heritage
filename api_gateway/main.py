"""
API Gateway — FastAPI application.
Orchestrates requests to internal services and exposes user-facing REST endpoints.

Routes:
  - POST /api/v1/trips/recommend    — Generate heritage travel itinerary
  - GET  /api/v1/heritage-sites      — List all heritage sites
  - GET  /api/v1/restaurants         — List all restaurants
  - GET  /api/v1/health               — Health check
  - GET  /                          — Serve MapLibre HTML frontend
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx

from config import settings

app = FastAPI(
    title="Vietnam Heritage Travel API Gateway",
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

import os
project_root = os.path.dirname(os.path.dirname(__file__))
frontend_dir = os.path.join(project_root, "frontend")
frontend_dist_dir = os.path.join(frontend_dir, "dist")
frontend_assets_dir = os.path.join(frontend_dist_dir, "assets")
if os.path.exists(frontend_assets_dir):
    app.mount("/assets", StaticFiles(directory=frontend_assets_dir), name="frontend-assets")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
async def root():
    """Serve the built React frontend when the gateway is used directly."""
    react_path = os.path.join(frontend_dist_dir, "index.html")
    if os.path.exists(react_path):
        return FileResponse(react_path)
    return {"message": "Vietnam Heritage Travel API Gateway", "docs": "/docs"}


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


@app.post("/api/v1/trips/recommend")
async def recommend_trip(payload: dict):
    """Forward trip recommendation request to AI service."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.ai_service_url}/api/v1/recommend",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=_error_detail(e))
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {str(e)}")


@app.post("/api/v1/routes/plan")
async def route_plan(payload: dict):
    """Forward fixed start/end route planning request to AI service."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.ai_service_url}/api/v1/routes/plan",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=_error_detail(e))
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {str(e)}")


@app.get("/api/v1/heritage-sites")
async def list_heritage_sites(province: str | None = None):
    """List heritage sites, optionally filtered by province."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.ai_service_url}/api/v1/heritage-sites",
            )
            resp.raise_for_status()
            data = resp.json()
            if province:
                data = [s for s in data if s.get("province") == province]
            return data
    except httpx.RequestError as e:
        sites = await _load_local_sites()
        if province:
            sites = [s for s in sites if s.get("province") == province]
        return sites


@app.get("/api/v1/heritage-sites/{site_id}/reviews")
async def get_site_reviews(site_id: str):
    """Forward reviews request to AI service."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.ai_service_url}/api/v1/heritage-sites/{site_id}/reviews",
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="AI service unavailable")


@app.get("/api/v1/heritage-sites/{site_id}/enrich")
async def enrich_site(site_id: str):
    """Forward enrich request to AI service."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{settings.ai_service_url}/api/v1/heritage-sites/{site_id}/enrich",
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="AI service unavailable")


@app.get("/api/v1/heritage-sites/{site_id}/images")
async def get_site_images(site_id: str):
    """Forward image request to AI service."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.ai_service_url}/api/v1/heritage-sites/{site_id}/images",
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="AI service unavailable")


@app.get("/api/v1/heritage-sites/{site_id}/narrate")
async def get_site_narration(site_id: str):
    """Forward narration request to AI service."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{settings.ai_service_url}/api/v1/heritage-sites/{site_id}/narrate",
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=_error_detail(e))
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="AI service unavailable")


@app.get("/api/v1/heritage-sites/{site_id}")
async def get_heritage_site(site_id: str):
    """Get a single heritage site by ID."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.ai_service_url}/api/v1/heritage-sites/{site_id}",
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="AI service unavailable")


@app.get("/api/v1/heritage-sites/{site_id}/reviews")
async def get_site_reviews(site_id: str):
    """Forward reviews request to AI service."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.ai_service_url}/api/v1/heritage-sites/{site_id}/reviews",
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="AI service unavailable")


@app.get("/api/v1/heritage-sites/{site_id}/enrich")
async def enrich_site(site_id: str):
    """Forward enrich request to AI service."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.ai_service_url}/api/v1/heritage-sites/{site_id}/enrich",
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="AI service unavailable")


async def _load_local_sites():
    """Fallback: load sites from local seed data."""
    return []


def _error_detail(error: httpx.HTTPStatusError):
    try:
        return error.response.json().get("detail", error.response.text)
    except Exception:
        return error.response.text or str(error)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
