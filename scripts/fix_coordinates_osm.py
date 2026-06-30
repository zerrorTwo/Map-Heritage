import json
import time
import urllib.request
import urllib.parse
import re

def search_osm(name, province):
    # Try searching with name and province
    query = f"{name}, {province}, Vietnam"
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit=1"
    req = urllib.request.Request(url, headers={'User-Agent': 'HeritageTravelApp/1.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print(f"Error searching {query}: {e}")
        
    # Fallback to just name
    time.sleep(1.1)
    query = f"{name}, Vietnam"
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit=1"
    req = urllib.request.Request(url, headers={'User-Agent': 'HeritageTravelApp/1.0'})
    
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
    except Exception as e:
        print(f"Error searching {query}: {e}")
        
    return None, None

def main():
    print("Starting OSM coordinate correction script...")
    
    # We will read curated_data.py, parse the lines, and update the lat/lng.
    # This is a basic string replacement approach.
    with open("services/ai_service/curated_data.py", "r", encoding="utf-8") as f:
        content = f.read()
        
    # Find all sites
    pattern = r'name="([^"]+)",\s*province="([^"]+)",\s*lat=([\d\.\-]+),\s*lng=([\d\.\-]+),'
    matches = re.finditer(pattern, content)
    
    new_content = content
    updated = 0
    not_found = 0
    
    for match in matches:
        name = match.group(1)
        province = match.group(2)
        old_lat = float(match.group(3))
        old_lng = float(match.group(4))
        
        print(f"[{updated+not_found+1}/1370] Searching OSM for '{name}' in {province}...")
        lat, lng = search_osm(name, province)
        
        if lat and lng:
            # Check if it's a significant change
            if abs(lat - old_lat) > 0.0001 or abs(lng - old_lng) > 0.0001:
                old_str = match.group(0)
                new_str = f'name="{name}",\n        province="{province}",\n        lat={lat:.6f}, lng={lng:.6f},'
                new_content = new_content.replace(old_str, new_str)
                updated += 1
                print(f"  -> Updated: {lat:.6f}, {lng:.6f}")
            else:
                print("  -> Kept original (already close)")
        else:
            not_found += 1
            print("  -> Not found on OSM")
            
        # Respect Nominatim API limits (1 request per second)
        time.sleep(1.1)
        
        # Save progress every 50 updates
        if updated % 50 == 0 and updated > 0:
            with open("services/ai_service/curated_data.py", "w", encoding="utf-8") as f:
                f.write(new_content)
                
    with open("services/ai_service/curated_data.py", "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print(f"\nDone! Updated {updated} sites. Could not find {not_found} sites.")

if __name__ == "__main__":
    main()
