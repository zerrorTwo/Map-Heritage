"""
AI Service — FastAPI application.
Implements the core recommendation engine REST API.
"""

from contextlib import asynccontextmanager
from typing import List
import urllib.parse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from services.ai_service.models import (
    HeritageSite, Restaurant, TripInput, TripRequest, Itinerary, Review,
)
from services.ai_service.pipeline import pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load curated data
    from services.ai_service.data_loader import load_all_data
    sites, restaurants = load_all_data()
    pipeline.load_data(sites, restaurants)
    print(f"Loaded {len(sites)} heritage sites + {len(restaurants)} restaurants")

    # Start background image populator (fetches + stores in DB)
    from services.image_service.batch_populator import populate_all
    import threading
    def progress(done, total, found):
        if done % 50 == 0 or done == total:
            print(f"  Image populate: {done}/{total} ({found} with images)")

    def run_populator():
        populate_all(progress_callback=progress)

    t = threading.Thread(target=run_populator, daemon=True)
    t.start()
    print("Background image populator started")
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


@app.get("/api/v1/heritage-sites/{site_id}/images")
async def get_site_images(site_id: str):
    """Get images for a heritage site from persistent store. Guarantees images via SVG fallback."""
    from services.image_service.image_store import get_images, store_images
    from services.image_service.batch_populator import fetch_images_for_site

    site = None
    for s in pipeline._sites_cache:
        if s.id == site_id:
            site = s
            break
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    # Check store first
    images = get_images(site_id)
    if images:
        return {"site_id": site_id, "name": site.name, "images": images, "source": "store"}

    # Try live fetch
    try:
        images = fetch_images_for_site(site.name, site.province, site.reference_url or "")
    except Exception:
        images = []
    if images:
        store_images(site_id, images)
        return {"site_id": site_id, "name": site.name, "images": images, "source": "live"}

    # Generate SVG placeholders (3 per site) so frontend always shows images
    cat_icons = {
        'spiritual': '🕌', 'history': '🏛️', 'architecture': '🏗️',
        'nature': '🏔️', 'museum': '🏛️', 'craft_village': '🎨',
        'unesco': '🌐', 'entertainment': '🎡'
    }
    icon = cat_icons.get(site.categories[0] if site.categories else 'history', '📍')
    colors = ['#e94560', '#f0a500', '#4a90d9']
    
    placeholders = []
    for i, color in enumerate(colors):
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="250" viewBox="0 0 400 250">
  <rect width="400" height="250" fill="#12121f"/>
  <rect x="10" y="10" width="380" height="230" rx="12" fill="none" stroke="{color}" stroke-width="2" opacity="0.4"/>
  <circle cx="200" cy="80" r="35" fill="{color}" opacity="0.15"/>
  <text x="200" y="95" text-anchor="middle" font-size="36">{icon}</text>
  <text x="200" y="150" text-anchor="middle" font-size="16" fill="#ddd" font-family="sans-serif">{site.name}</text>
  <text x="200" y="175" text-anchor="middle" font-size="12" fill="#888" font-family="sans-serif">📍 {site.province}</text>
  <text x="200" y="205" text-anchor="middle" font-size="10" fill="{color}" font-family="sans-serif">Đang tải ảnh từ Wikipedia...</text>
</svg>'''
        data_uri = f"data:image/svg+xml,{urllib.parse.quote(svg)}"
        placeholders.append({
            "thumb_url": data_uri,
            "url": data_uri,
            "title": f"{site.name} - {site.province}",
        })
    
    return {"site_id": site_id, "name": site.name, "images": placeholders, "source": "placeholder"}


@app.get("/api/v1/images/stats")
async def image_stats():
    """Get image storage statistics."""
    from services.image_service.image_store import get_stats
    return get_stats()


@app.get("/api/v1/heritage-sites/{site_id}/reviews", response_model=List[Review])
async def get_reviews(site_id: str):
    """Get reviews for a heritage site."""
    from services.image_service.enricher import generate_reviews
    site = None
    for s in pipeline._sites_cache:
        if s.id == site_id:
            site = s
            break
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return generate_reviews(site.name, site.province, site.popularity_score)


@app.get("/api/v1/heritage-sites/{site_id}/enrich")
async def enrich_site_info(site_id: str):
    """Get enriched description from Wikipedia."""
    from services.image_service.enricher import enrich_site
    site = None
    for s in pipeline._sites_cache:
        if s.id == site_id:
            site = s
            break
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    data = enrich_site(site.name, site.province, site.reference_url or "")
    return {"site_id": site_id, "name": site.name, **data}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
