import json, re

with open("locations_updated.json", "r", encoding="utf-8") as f:
    locations = json.load(f)

# Create a lookup dictionary
lookup = {}
for loc in locations:
    key = f"{loc['name']}|{loc['province']}"
    lookup[key] = (loc['lat'], loc['lng'])

with open("services/ai_service/curated_data.py", "r", encoding="utf-8") as f:
    content = f.read()

pattern = r'name="([^"]+)",\s*province="([^"]+)",\s*lat=([\d\.\-]+),\s*lng=([\d\.\-]+),'
matches = re.finditer(pattern, content)

new_content = content
updated = 0
for match in matches:
    name = match.group(1)
    province = match.group(2)
    key = f"{name}|{province}"
    if key in lookup:
        lat, lng = lookup[key]
        old_str = match.group(0)
        new_str = f'name="{name}",\n        province="{province}",\n        lat={lat}, lng={lng},'
        new_content = new_content.replace(old_str, new_str)
        updated += 1

with open("services/ai_service/curated_data.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"Updated {updated} sites!")
