"""
API Gateway — FastAPI application.
Only exposes AI recommendation endpoints.
Heritage data endpoints are served by Heritage-LastDance-BE.

Routes:
  - POST /api/v1/trips/recommend    — Generate heritage travel itinerary
  - POST /api/v1/routes/plan        — Plan a fixed start/end route
  - GET  /api/v1/health             — Health check
  - GET  /                          — Gateway health & docs
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx

from config import settings

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


def _error_detail(error: httpx.HTTPStatusError):
    try:
        return error.response.json().get("detail", error.response.text)
    except Exception:
        return error.response.text or str(error)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
