import sys
import os
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.ai_service.ttdp_solver import solve_ttdp, haversine

def test_haversine():
    dist = haversine(21.0285, 105.8542, 21.0300, 105.8500)
    assert dist > 0
    assert 200 < dist < 800

def test_ttdp_basic():
    # 0 is start, 1 is end, 2-5 are POIs
    locations = [
        (21.0000, 105.8000), # Start
        (21.0000, 105.8000), # End
        (21.0100, 105.8100), # POI 1: close, high score
        (21.0200, 105.8200), # POI 2: medium dist, med score
        (21.0900, 105.8900), # POI 3: very far, high score
        (21.0050, 105.8050), # POI 4: very close, low score
    ]
    scores = [0.0, 0.0, 0.9, 0.5, 0.9, 0.2]
    durations = [0, 0, 3600, 3600, 3600, 3600]
    
    # Very wide time windows
    time_windows = [(0, 100000)] * 6
    
    routes = solve_ttdp(
        locations, scores, durations, time_windows,
        num_days=1, max_time_per_day=4 * 3600, speed_kmh=40.0
    )
    
    assert len(routes) == 1
    route = routes[0]
    
    print("Computed Route:", route)
    assert len(route) > 0
