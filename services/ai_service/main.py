"""
AI Service — FastAPI application.
Implements the core recommendation engine REST API.
"""

from contextlib import asynccontextmanager
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.ai_service.models import (
    HeritageSite, Restaurant, TripInput, TripRequest, Itinerary,
)
from services.ai_service.pipeline import pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load crawled OSM data + curated seed data
    from services.ai_service.data_loader import load_all_data
    sites, restaurants = load_all_data()
    pipeline.load_data(sites, restaurants)
    print(f"Loaded {len(sites)} heritage sites + {len(restaurants)} restaurants from real OSM data")
    yield


app = FastAPI(
    title="Vietnam Heritage Travel AI Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-service"}


@app.post("/api/v1/recommend", response_model=Itinerary)
async def recommend(input_data: TripInput):
    """Recommend a heritage travel itinerary based on user input."""
    try:
        itinerary = await pipeline.run(input_data)
        return itinerary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/heritage-sites", response_model=List[HeritageSite])
async def list_sites():
    """List all available heritage sites."""
    return pipeline._sites_cache


@app.get("/api/v1/restaurants", response_model=List[Restaurant])
async def list_restaurants():
    """List all available restaurants."""
    return pipeline._restaurants_cache


@app.get("/api/v1/heritage-sites/{site_id}", response_model=HeritageSite)
async def get_site(site_id: str):
    for site in pipeline._sites_cache:
        if site.id == site_id:
            return site
    raise HTTPException(status_code=404, detail="Site not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
