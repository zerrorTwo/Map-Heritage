# Vietnam Heritage Travel — Data

## Source
All data crawled from **OpenStreetMap** via the [Overpass API](http://overpass-api.de/api/interpreter) (free, no API key).

## Files
- `crawled_heritage.json` — 376 heritage sites across Vietnam (temples, museums, monuments, historic sites)
- `crawled_restaurants.json` — 359 restaurants & cafes across Vietnam

## Crawl date
June 2026

## Regenerate
```bash
cd /path/to/Map
PYTHONPATH=. python3 services/data_crawler/regional_crawler.py
```

Or use the simpler single-query approach:
```bash
PYTHONPATH=. python3 -c "
from services.data_crawler.overpass_crawler import crawl_heritage_sites, crawl_restaurants
import json
sites = crawl_heritage_sites(500)
rests = crawl_restaurants(500)
json.dump(sites, open('data/crawled_heritage.json','w'), ensure_ascii=False, indent=2)
json.dump(rests, open('data/crawled_restaurants.json','w'), ensure_ascii=False, indent=2)
"
```

## Filtering
- Vietnam geographic bounding box: lat 8.3–23.2, lng 102.3–109.3
- Non-Vietnamese scripts filtered out (Thai, Khmer, Lao, Burmese)
- Known non-VN place names excluded

## License
OpenStreetMap data © OpenStreetMap contributors, licensed under ODbL.
