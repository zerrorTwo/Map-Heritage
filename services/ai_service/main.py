"""
AI Service — FastAPI application.
Core recommendation engine REST API.
"""

import contextvars
import logging
import time
import uuid
import urllib.parse
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from config.logging_config import setup_logging

setup_logging(level=settings.log_level, log_dir=settings.log_dir, log_file=settings.log_file)
log = logging.getLogger("heritage.api")
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

from services.ai_service.models import (
    HeritageSite, TripInput, TripRequest, Itinerary, Review,
    RoutePlanRequest, RoutePlanResponse,
)
from services.ai_service.pipeline import pipeline
from services.ai_service.route_planner import plan_route


@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.ai_service.data_loader import load_all_data
    try:
        sites, _ = load_all_data()
        pipeline.load_data(sites)
        log.info("Data loaded: %d heritage sites", len(sites))
    except Exception as e:
        log.critical("Failed to load heritage data: %s", e, exc_info=True)
        raise
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


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])
    request_id_var.set(req_id)

    t0 = time.time()
    try:
        response = await call_next(request)
    except Exception:
        ms = int((time.time() - t0) * 1000)
        log.exception("[%s] %s %s → 500  %dms", req_id, request.method, request.url.path, ms)
        raise

    ms = int((time.time() - t0) * 1000)
    log.info("[%s] %s %s → %s  %dms",
             req_id, request.method, request.url.path, response.status_code, ms)
    response.headers["X-Request-ID"] = req_id
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-service", "sites": len(pipeline._sites_cache)}


@app.post("/api/v1/recommend", response_model=Itinerary)
async def recommend(input_data: TripInput):
    try:
        itinerary = await pipeline.run(input_data)
        return itinerary
    except Exception as e:
        log.exception("recommend failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/routes/plan", response_model=RoutePlanResponse)
async def route_plan(input_data: RoutePlanRequest):
    import asyncio
    try:
        return await asyncio.to_thread(plan_route, input_data)
    except Exception as e:
        log.exception("route_plan failed")
        return RoutePlanResponse(status="error", warnings=[str(e)])


@app.get("/api/v1/heritage-sites", response_model=List[HeritageSite])
async def list_sites():
    return pipeline._sites_cache


@app.get("/api/v1/heritage-sites/{site_id}", response_model=HeritageSite)
async def get_site(site_id: str):
    for site in pipeline._sites_cache:
        if site.id == site_id:
            return site
    raise HTTPException(status_code=404, detail="Site not found")


@app.get("/api/v1/heritage-sites/{site_id}/images")
async def get_site_images(site_id: str):
    from services.image_service.image_store import get_images, store_images
    from services.image_service.batch_populator import fetch_images_for_site

    site = None
    for s in pipeline._sites_cache:
        if s.id == site_id:
            site = s
            break
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    images = get_images(site_id)
    if images:
        return {"site_id": site_id, "name": site.name, "images": images, "source": "store"}

    try:
        images = fetch_images_for_site(site.name, site.province, site.reference_url or "")
    except Exception:
        log.warning("Image fetch failed for %s", site_id, exc_info=True)
        images = []
    if images:
        store_images(site_id, images)
        return {"site_id": site_id, "name": site.name, "images": images, "source": "live"}

    cat_icons = {
        'spiritual': '\U0001f54c', 'history': '\U0001f3db\ufe0f', 'architecture': '\U0001f3d7\ufe0f',
        'nature': '\U0001f3d4\ufe0f', 'museum': '\U0001f3db\ufe0f', 'craft_village': '\U0001f3a8',
        'unesco': '\U0001f310', 'entertainment': '\U0001f3a1'
    }
    icon = cat_icons.get(site.categories[0] if site.categories else 'history', '\U0001f4cd')
    colors = ['#e94560', '#f0a500', '#4a90d9']

    placeholders = []
    for i, color in enumerate(colors):
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="250" viewBox="0 0 400 250">
  <rect width="400" height="250" fill="#12121f"/>
  <rect x="10" y="10" width="380" height="230" rx="12" fill="none" stroke="{color}" stroke-width="2" opacity="0.4"/>
  <circle cx="200" cy="80" r="35" fill="{color}" opacity="0.15"/>
  <text x="200" y="95" text-anchor="middle" font-size="36">{icon}</text>
  <text x="200" y="150" text-anchor="middle" font-size="16" fill="#ddd" font-family="sans-serif">{site.name}</text>
  <text x="200" y="175" text-anchor="middle" font-size="12" fill="#888" font-family="sans-serif">\U0001f4cd {site.province}</text>
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
    from services.image_service.image_store import get_stats
    return get_stats()


@app.get("/api/v1/heritage-sites/{site_id}/reviews", response_model=List[Review])
async def get_reviews(site_id: str):
    from services.image_service.persistent_store import get_reviews, save_reviews
    from services.image_service.enricher import generate_reviews

    site = None
    for s in pipeline._sites_cache:
        if s.id == site_id:
            site = s
            break
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    cached = get_reviews(site_id)
    if cached:
        return cached

    reviews = generate_reviews(site.name, site.province, site.popularity_score)
    save_reviews(site_id, reviews)
    return reviews


@app.get("/api/v1/heritage-sites/{site_id}/enrich")
async def enrich_site_info(site_id: str):
    from services.image_service.persistent_store import get_enriched, save_enriched
    from services.image_service.enricher import enrich_site

    site = None
    for s in pipeline._sites_cache:
        if s.id == site_id:
            site = s
            break
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    cached = get_enriched(site_id)
    if cached and len(cached.get("long_description", "")) >= 220:
        return {"site_id": site_id, "name": site.name, **cached}

    data = enrich_site(site.name, site.province, site.reference_url or "")
    save_enriched(site_id, data)
    return {"site_id": site_id, "name": site.name, **data}


@app.get("/api/v1/heritage-sites/{site_id}/narrate")
async def get_site_narration(site_id: str):
    site = None
    for s in pipeline._sites_cache:
        if s.id == site_id:
            site = s
            break
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    import urllib.request
    import json

    summary = ""
    try:
        query = urllib.parse.quote(site.name)
        url = f"https://vi.wikipedia.org/w/api.php?format=json&action=query&prop=extracts&exintro&explaintext&redirects=1&titles={query}"
        req = urllib.request.Request(url, headers={'User-Agent': 'HeritageTravelApp/1.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json.loads(response.read().decode())
            pages = data['query']['pages']
            page = list(pages.values())[0]
            if 'extract' in page:
                summary = page['extract'][:500] + "..." if len(page['extract']) > 500 else page['extract']
    except Exception:
        pass

    fallback = site.long_description or site.description or "Hiện chưa có thông tin chi tiết về địa điểm này."
    final_text = summary if summary and len(summary) > 50 else fallback

    return {"site_id": site_id, "name": site.name, "narration": final_text}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
