"""
DuckDuckGo Image Fetcher — Free, no API key.
Uses DuckDuckGo Instant Answer API to get images for landmarks.
"""

import json, urllib.request, urllib.parse, time, os
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

DDG_API = "https://api.duckduckgo.com/"
CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "wiki_images.json")


def search_ddg_image(query: str, timeout: int = 8) -> Optional[dict]:
    """Search DuckDuckGo for an image about a topic. Returns {thumb_url, title} or None."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "t": "heritage_planner",
        "no_html": "1",
        "skip_disambig": "1",
    })
    url = DDG_API + "?" + params
    req = urllib.request.Request(url, headers={"User-Agent": "HeritagePlanner/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return None

    image_path = data.get("Image", "")
    if image_path:
        return {
            "thumb_url": f"https://duckduckgo.com{image_path}",
            "title": data.get("Heading", query),
            "abstract": data.get("Abstract", "")[:200],
            "source_url": data.get("AbstractURL", ""),
        }
    return None


def fetch_all_images(sites: list, max_workers: int = 5) -> Dict[str, dict]:
    """Fetch images for all sites using DuckDuckGo API in parallel."""
    results = {}
    tasks = []

    for s in sites:
        sid = s.get("id", "")
        name = s.get("name", "")
        province = s.get("province", "")
        if sid in results:
            continue
        # Query with name + Vietnam for better results
        query = f"{name} {province} Vietnam"
        tasks.append((sid, name, query))

    def fetch_one(sid, name, query):
        data = search_ddg_image(query, timeout=8)
        if data:
            return (sid, data)
        # Retry with just name + "Vietnam"
        data = search_ddg_image(f"{name} Vietnam", timeout=8)
        if data:
            return (sid, data)
        return None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, *t): t for t in tasks}
        for f in as_completed(futures):
            result = f.result()
            if result:
                sid, data = result
                results[sid] = data

    return results


def merge_with_cache(existing_cache: dict, new_images: dict):
    """Merge new images into existing cache, keeping existing ones."""
    for sid, data in new_images.items():
        if sid not in existing_cache:
            existing_cache[sid] = data
    return existing_cache


def load_cache() -> dict:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    
    with open(os.path.join(os.path.dirname(CACHE_PATH), "deepseek_clean.json")) as f:
        sites = json.load(f)
    
    cache = load_cache()
    missing = [s for s in sites if s["id"] not in cache]
    print(f"Cached: {len(cache)}, Missing: {len(missing)}")
    
    if missing:
        print(f"Fetching images for {len(missing)} sites via DuckDuckGo...")
        new = fetch_all_images(missing, max_workers=5)
        cache.update(new)
        save_cache(cache)
        print(f"Added {len(new)} images, total: {len(cache)}")
    
    # Show sample
    for sid, data in list(cache.items())[:3]:
        print(f"  {data.get('title','?')[:40]}: {data.get('thumb_url','')[:70]}...")
