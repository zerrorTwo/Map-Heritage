import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to sys.path so imports work
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from services.ai_service.data_loader import load_all_data
from services.image_service.persistent_store import get_enriched, save_enriched
from services.image_service.enricher import enrich_site

def process_site(site):
    site_id = site.id
    name = site.name
    province = site.province
    ref_url = site.reference_url or ""
    
    # Check if already cached
    cached = get_enriched(site_id)
    if cached:
        return site_id, name, True # True means it was cached
    
    try:
        # Fetch data
        data = enrich_site(name, province, ref_url)
        # Save data
        save_enriched(site_id, data)
        return site_id, name, False # False means newly fetched
    except Exception as e:
        print(f"Error enriching {name} ({site_id}): {e}")
        return site_id, name, None

def prefetch_all(max_workers=10):
    print("Loading all heritage sites...")
    sites, _ = load_all_data()
    print(f"Found {len(sites)} sites. Starting enrichment process with {max_workers} threads...")
    
    cached_count = 0
    fetched_count = 0
    error_count = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_site, site): site for site in sites}
        
        for i, future in enumerate(as_completed(futures), 1):
            site = futures[future]
            try:
                site_id, name, was_cached = future.result()
                if was_cached is True:
                    cached_count += 1
                elif was_cached is False:
                    fetched_count += 1
                else:
                    error_count += 1
                    
                if i % 10 == 0 or i == len(sites):
                    print(f"Progress: {i}/{len(sites)} (Fetched: {fetched_count}, Cached: {cached_count}, Errors: {error_count})")
            except Exception as exc:
                print(f"Site {site.name} generated an exception: {exc}")
                error_count += 1
                
    print("\nEnrichment process completed!")
    print(f"Total sites: {len(sites)}")
    print(f"Newly fetched: {fetched_count}")
    print(f"Already cached: {cached_count}")
    print(f"Errors: {error_count}")

if __name__ == "__main__":
    prefetch_all(max_workers=10)
