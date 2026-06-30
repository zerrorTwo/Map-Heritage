import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.ai_service.models import TripInput, HeritageSite
from services.ai_service.pipeline import pipeline

async def test_recommend():
    sites = [
        HeritageSite(
            id=str(i),
            name=f"Site {i}",
            lat=21.0 + i*0.01,
            lng=105.8 + i*0.01,
            province="Hà Nội",
            categories=["culture"]
        ) for i in range(10)
    ]
    pipeline.load_data(sites)
    
    trip_input = TripInput(
        raw_text="Test trip",
        start_lat=21.0,
        start_lng=105.8,
        destination_provinces=["Hà Nội"],
        duration_days=2,
        pace="moderate",
        interests=["culture"]
    )
    
    itinerary = await pipeline.run(trip_input)
    print("Generated days:", len(itinerary.days))
    for d in itinerary.days:
        print(f"Day plan size: {len(d.items)}")
        
if __name__ == "__main__":
    asyncio.run(test_recommend())
