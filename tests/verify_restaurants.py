"""Verify restaurants are inserted and food_score > 0."""
import sys, asyncio
sys.path.insert(0, r"D:\Nam\Map-Heritage")

from services.ai_service.models import TripInput
from services.ai_service.data_loader import load_all_data
from services.ai_service.pipeline import Pipeline
from services.ai_service.step1_normalizer import parse_trip_request
from services.ai_service.step2_candidates import generate_candidates
from services.ai_service.step3_weather import weather_service
from services.ai_service.step4_scoring import score_all_sites

async def main():
    sites, restaurants = load_all_data()
    print(f"Loaded {len(sites)} sites, {len(restaurants)} restaurants")

    p = Pipeline()
    p.load_data(sites, restaurants)

    # Test with food preferences
    inp = TripInput(
        destination_area="Ha Nội",
        destination_provinces=["Hà Nội"],
        duration_days=2,
        interests=["history", "architecture"],
        food_preferences=["pho", "bun"],
        pace="moderate"
    )

    result = await p.run(inp)
    print(f"\nItinerary ID: {result.itinerary_id}")
    print(f"Total score: {result.total_score:.4f}")
    print(f"Total distance: {result.total_distance_km} km")
    print(f"Days: {len(result.days)}")

    total_heritage = 0
    total_restaurants = 0
    for day in result.days:
        for item in day.items:
            if item.type == "heritage":
                total_heritage += 1
            elif item.type == "restaurant":
                total_restaurants += 1
        print(f"  Day {day.day}: {len(day.items)} stops ({[f'{it.type[0]}:{it.name[:15]}' for it in day.items]})")

    print(f"\nHeritage: {total_heritage}, Restaurants: {total_restaurants}")
    print(f"Food score component: {min(1.0, total_restaurants / max(1, len(result.days) * 3)):.4f}")
    print(f"Summary: {result.summary}")

    assert total_restaurants > 0, "FAIL: no restaurants inserted!"
    print("\nSUCCESS: restaurants are being inserted and food_score > 0")

asyncio.run(main())
