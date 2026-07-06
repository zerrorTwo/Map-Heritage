"""Diagnostic: compute average scores across configurations using real data."""
import sys, asyncio
sys.path.insert(0, r"D:\Nam\Map-Heritage")

from services.ai_service.models import TripInput, TripRequest, Forecast, ScoredSite
from services.ai_service.step1_normalizer import parse_trip_request
from services.ai_service.step2_candidates import generate_candidates
from services.ai_service.step4_scoring import score_all_sites
from services.ai_service.data_loader import load_all_data


async def main():
    sites, _ = load_all_data()
    provinces = sorted(set(s.province for s in sites))
    categories = sorted(set(c for s in sites for c in s.categories))
    print(f"Loaded {len(sites)} sites across {len(provinces)} provinces")
    print(f"Province sample: {provinces[:15]}")
    print(f"Category sample: {categories[:20]}")
    print()

    configs = [
        # (label, TripInput)
        ("HN-history-1day", TripInput(destination_area="Hà Nội", destination_provinces=["Hà Nội"], duration_days=1, interests=["history", "architecture"], pace="moderate")),
        ("HN-history-3day", TripInput(destination_area="Hà Nội", destination_provinces=["Hà Nội"], duration_days=3, interests=["history", "architecture"], pace="moderate")),
        ("HN-food-1day", TripInput(destination_area="Hà Nội", destination_provinces=["Hà Nội"], duration_days=1, interests=["local_food", "culture"], pace="relaxed")),
        ("HN-spiritual-1day", TripInput(destination_area="Hà Nội", destination_provinces=["Hà Nội"], duration_days=1, interests=["spiritual", "history"], pace="moderate")),
        ("HN-elderly-1day", TripInput(destination_area="Hà Nội", destination_provinces=["Hà Nội"], duration_days=1, interests=["history"], constraints=["elderly_friendly"], pace="relaxed")),
        ("HN-lowbudget-1day", TripInput(destination_area="Hà Nội", destination_provinces=["Hà Nội"], duration_days=1, interests=["history"], budget_level="low", pace="moderate")),
        ("Hue-history-1day", TripInput(destination_area="Huế", destination_provinces=["Thừa Thiên Huế"], duration_days=1, interests=["history", "architecture"], pace="moderate")),
        ("HCM-history-1day", TripInput(destination_area="Hồ Chí Minh", destination_provinces=["Hồ Chí Minh"], duration_days=1, interests=["history", "museum"], pace="moderate")),
        ("DN-nature-1day", TripInput(destination_area="Đà Nẵng", destination_provinces=["Đà Nẵng"], duration_days=1, interests=["nature", "photography"], pace="moderate")),
        ("Multi-foodie-3day", TripInput(destination_area="Hà Nội", destination_provinces=["Hà Nội"], duration_days=3, interests=["local_food", "culture", "photography"], pace="moderate")),
    ]

    print(f"{'Config':<25} {'Candidates':>10} {'Scored':>6} {'Avg Score':>10} {'Max':>8} {'Min':>8}")
    print("-" * 75)

    for label, inp in configs:
        trip = parse_trip_request(inp)
        candidates = generate_candidates(trip, sites, top_n=50)

        dummy_fcasts = {s.id: [Forecast(date="2026-07-06", hour=10, temperature_c=28, rain_probability=10, uv_index=4)] for s in candidates}
        scored = score_all_sites(candidates, trip, dummy_fcasts)

        if scored:
            avg = sum(s.score for s in scored) / len(scored)
            mx = max(s.score for s in scored)
            mn = min(s.score for s in scored)
        else:
            avg = mx = mn = 0.0

        print(f"{label:<25} {len(candidates):>10} {len(scored):>6} {avg:>10.4f} {mx:>8.4f} {mn:>8.4f}")

    # Overall distribution across all scored sites
    print(f"\n--- Score distribution (all {len([c for _, inp in configs for c in generate_candidates(parse_trip_request(inp), sites, top_n=50)])} scored) ---")
    import numpy as np
    all_scores = []
    for label, inp in configs:
        trip = parse_trip_request(inp)
        candidates = generate_candidates(trip, sites, top_n=50)
        dummy_fcasts = {s.id: [Forecast(date="2026-07-06", hour=10)] for s in candidates}
        scored = score_all_sites(candidates, trip, dummy_fcasts)
        all_scores.extend(s.score for s in scored)

    arr = np.array(all_scores)
    print(f"  Count: {len(arr)}")
    print(f"  Mean:  {arr.mean():.4f}")
    print(f"  Median: {np.median(arr):.4f}")
    print(f"  Std:   {arr.std():.4f}")
    print(f"  Min:   {arr.min():.4f}")
    print(f"  Max:   {arr.max():.4f}")
    print(f"  P10:   {np.percentile(arr, 10):.4f}")
    print(f"  P25:   {np.percentile(arr, 25):.4f}")
    print(f"  P75:   {np.percentile(arr, 75):.4f}")
    print(f"  P90:   {np.percentile(arr, 90):.4f}")

asyncio.run(main())
