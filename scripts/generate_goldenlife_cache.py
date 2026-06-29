#!/usr/bin/env python3
"""
Parse /tmp/goldenlife_raw.html to extract Goldenlife images with context,
match them to curated heritage sites via fuzzy string matching,
and merge into /workspace/Map/data/wiki_images.json cache.
Also extracts province->[sites] listing to /tmp/goldenlife_provinces.json.
"""

import json
import re
import os
import sys
import unicodedata
from difflib import SequenceMatcher
from lxml import html
from typing import Dict, List, Optional, Tuple

# ── Paths ──────────────────────────────────────────────────────────────────
HTML_PATH = "/tmp/goldenlife_raw.html"
CACHE_PATH = "/workspace/Map/data/wiki_images.json"
PROVINCES_JSON_PATH = "/tmp/goldenlife_provinces.json"

# ── Helpers ────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    s = s.lower()
    s = s.replace('đ', 'd')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^\w\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


KNOWN_PROVINCES_NORM = {
    "ha noi", "bac ninh", "ninh binh", "ha nam", "hai phong",
    "hai duong", "hung yen", "nam dinh", "thai binh", "vinh phuc",
    "ha giang", "cao bang", "bac can", "lang son", "tuyen quang",
    "thai nguyen", "phu tho", "bac giang", "quang ninh", "lao cai",
    "yen bai", "dien bien", "hoa binh", "lai chau", "son la",
    "thanh hoa", "nghe an", "ha tinh", "quang binh", "quang tri",
    "thua thien hue", "da nang", "quang nam", "quang ngai",
    "binh dinh", "phu yen", "khanh hoa", "ninh thuan",
    "binh thuan", "kon tum", "gia lai", "dak lak", "dak nong",
    "lam dong", "ho chi minh",
    "dong nai", "binh duong", "binh phuoc", "tay ninh",
    "ba ria - vung tau", "long an", "tien giang",
    "ben tre", "tra vinh", "vinh long", "dong thap", "an giang",
    "kien giang", "can tho", "hau giang", "soc trang", "bac lieu",
    "ca mau",
}
KNOWN_PROVINCES_NORM.add("ha noi (ha tay)")  # merged province


def is_province_heading(text: str) -> Optional[str]:
    """If text looks like a province heading, return province name."""
    text = text.strip()
    m = re.match(r'^\d+\s*[\.\)]\s*(.+)$', text)
    if not m:
        return None
    name = m.group(1).strip()
    # Split on em-dash or hyphen
    name = re.split(r'\s*[–\-—]\s*', name, maxsplit=1)[0].strip()
    name = re.sub(r'\s*\(.*?\)\s*', '', name).strip()
    if not name:
        return None
    norm = normalize(name)
    if norm in KNOWN_PROVINCES_NORM:
        return name
    return None


def is_food_heading(text: str) -> bool:
    t = normalize(text)
    return any(kw in t for kw in ['mon ngon', 'am thuc', 'dac san'])


FOOD_TOKEN_BLACKLIST = {
    # Dishes / cooking methods (all normalized - no diacritics)
    'banh', 'bun', 'cha', 'pho', 'com', 'goi', 'che', 'mam', 'nuong', 'xoi',
    'chao', 'nem', 'lau', 'tom', 'ruoc', 'mang', 'oc', 'ga', 'bo', 'heo', 'vit',
    'muc', 'cua', 'dau', 'ran', 'chung', 'gio', 'kho', 'hap', 'cuon', 'cuon',
    'canh', 'nuoc', 'trang', 'mien', 'de', 'lon', 'ca', 'suon',
    'khau nhuc', 'thang co', 'pa pinh', 'com lam', 'rau don', 'nau', 'tuong',
    'lap suon', 'banh xeo', 'banh cuon', 'banh trang', 'banh chung',
    'banh gio', 'banh gai', 'banh duc', 'banh te', 'banh khuc',
    'nem chua', 'nem nuong', 'cha muc', 'cha ca', 'bun cha', 'bun bo',
    'pho bo', 'pho ga', 'bun rieu', 'bun oc',
    'ca kho', 'ca nuong', 'thit chuot', 'trau gac bep',
    'xoi ngu sac', 'xoi trung kien', 'chao long', 'mam tom', 'mam tep',
    'mam cay', 'ruou', 'kem', 'che lam', 'banh khao',
    'bap', 'mit', 'sau', 'xoai', 'dua', 'mit', 'nhau',
}


def is_likely_food(text: str) -> bool:
    """Check if the extracted site name is clearly about food."""
    norm = normalize(text)
    tokens = set(norm.split())
    matched = tokens & FOOD_TOKEN_BLACKLIST
    if len(matched) >= 2:
        return True
    # Single token match but text is short (just a dish name)
    if len(matched) >= 1 and len(tokens) <= 4:
        return True
    return False


def extract_site_name_from_entry(entry: Dict) -> Optional[str]:
    """Extract a clean site name from caption, alt, or filename."""
    candidates = []

    cap = entry.get("caption", "").strip()
    if cap:
        cap = re.sub(r'\.\d+jpg$', '', cap, flags=re.I)
        cap = re.sub(r'\s*[-–—]\s*ảnh internet\s*$', '', cap, flags=re.I)
        candidates.append(cap)

    alt = entry.get("alt", "").strip()
    if alt and alt.lower() not in ("image", ""):
        alt = re.sub(r'\.\d+jpg$', '', alt, flags=re.I)
        candidates.append(alt)

    url = entry.get("url", "")
    m = re.search(r'uploads/\d{4}/\d{2}/(.+?)\.\w+', url)
    if m:
        fname = m.group(1)
        fname = re.sub(r'-\d+x\d+(-\d+x\d+)*$', '', fname)
        fname = fname.replace('-', ' ').replace('_', ' ')
        if not re.match(r'^[\d\s\-]+$', fname):
            candidates.append(fname)

    for c in candidates:
        c = re.sub(r'\s+', ' ', c).strip()
        if len(c) > 3:
            return c
    return None


# ── Load curated sites ────────────────────────────────────────────────────

def load_curated_sites() -> List[Dict]:
    sys.path.insert(0, "/workspace/Map")
    from services.ai_service.curated_data import CURATED_HERITAGE
    return [{"id": h.id, "name": h.name, "province": h.province} for h in CURATED_HERITAGE]


# ── Parse HTML ─────────────────────────────────────────────────────────────

def parse_goldenlife_html(filepath: str) -> Tuple[List[Dict], Dict[str, List[str]]]:
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    tree = html.fromstring(raw)

    # Find the main blog content div
    blog_content = None
    for elem in tree.iter():
        cls = elem.get('class', '')
        if isinstance(cls, str) and 'blog-content-details' in cls:
            blog_content = elem
            break
    if blog_content is None:
        blog_content = tree

    entries = []
    province_sites: Dict[str, List[str]] = {}
    current_province = ""
    seen_food_heading = False
    seen_site_list = False  # have we already collected the site ul for this province?

    for elem in blog_content.iter():
        prov = None
        if elem.tag in ('h3', 'h4'):
            text = elem.text_content().strip() if elem.text_content() else ""
            prov = is_province_heading(text)
        elif elem.tag == 'p':
            text = elem.text_content().strip() if elem.text_content() else ""
            # Only match short p elements (likely inline province headings)
            if len(text) < 80:
                prov = is_province_heading(text)

        if prov:
            current_province = prov
            if current_province not in province_sites:
                province_sites[current_province] = []
            seen_food_heading = False
            seen_site_list = False
            continue

        if elem.tag in ('h3', 'h4', 'p'):
            text = elem.text_content().strip() if elem.text_content() else ""
            if is_food_heading(text):
                seen_food_heading = True
                continue

        # Collect UL items for the current province
        if elem.tag == 'ul' and current_province:
            items = []
            for li in elem:
                t = li.text_content().strip()
                if t and len(t) > 3:
                    items.append(t)

            if items:
                if not seen_food_heading and not seen_site_list:
                    # This is the site list
                    province_sites[current_province].extend(items)
                    seen_site_list = True
                # If seen_food_heading is True and we encounter another ul after food = food list, skip

        # Collect img tags
        if elem.tag == 'img':
            src = elem.get('src', '')
            if 'wp-content/uploads' not in src:
                continue
            if '/wp-content/themes/' in src:
                continue

            alt = elem.get('alt', '').strip()
            caption = ""
            parent = elem.getparent()
            if parent is not None:
                for child in parent.iter():
                    cls = child.get('class') or ''
                    if child.tag == 'p' and 'wp-caption-text' in cls:
                        caption = child.text_content().strip()
                        break

            entries.append({
                "url": src,
                "alt": alt,
                "caption": caption,
                "province": current_province,
            })

    return entries, province_sites


# ── Matching ───────────────────────────────────────────────────────────────

def detect_province_in_text(text: str) -> Optional[str]:
    """Detect province name from text."""
    norm = normalize(text)
    for prov in sorted(KNOWN_PROVINCES_NORM, key=len, reverse=True):
        prov_tokens = set(prov.split())
        if prov_tokens and prov_tokens.issubset(set(norm.split())):
            return prov
        if prov in norm and len(prov) >= 4:
            return prov
    return None


def match_entry_to_site(entry: Dict, curated: List[Dict]) -> Optional[str]:
    raw_name = extract_site_name_from_entry(entry)
    if not raw_name:
        return None

    # Skip entries that are clearly about food, not heritage sites
    if is_likely_food(raw_name):
        return None

    site_norm = normalize(raw_name)
    site_tokens = set(site_norm.split())
    site_tokens = {t for t in site_tokens if len(t) >= 2}
    if not site_tokens:
        return None

    html_prov = normalize(entry.get("province", ""))
    text_prov = detect_province_in_text(raw_name) or ""

    best_score = 0.0
    best_id = None

    for site in curated:
        cur_norm = normalize(site["name"])
        cur_prov = normalize(site["province"])
        cur_tokens = set(cur_norm.split())

        # Direct name similarity
        name_sim = SequenceMatcher(None, site_norm, cur_norm).ratio()

        # Substring containment
        substr_bonus = 0.0
        if len(site_norm) >= 4 and len(cur_norm) >= 4:
            if site_norm in cur_norm or cur_norm in site_norm:
                substr_bonus = 0.35

        # Token overlap
        token_overlap = 0.0
        if site_tokens and cur_tokens:
            common = site_tokens & cur_tokens
            token_overlap = len(common) / max(len(site_tokens), len(cur_tokens))

        # Province match
        prov_bonus = 0.0
        for dp in [html_prov, text_prov]:
            if not dp:
                continue
            if dp == cur_prov or fuzzy_score(dp, cur_prov) > 0.9:
                prov_bonus = max(prov_bonus, 0.25)
            elif fuzzy_score(dp, cur_prov) > 0.7:
                prov_bonus = max(prov_bonus, 0.1)

        score = name_sim * 0.35 + token_overlap * 0.25 + substr_bonus + prov_bonus

        if score > best_score:
            best_score = score
            best_id = site["id"]

    if best_score >= 0.50:
        return best_id
    return None


def fix_url(url: str) -> str:
    if url.startswith("http://goldenlife01.local/"):
        url = url.replace("http://goldenlife01.local/", "https://goldenlifetravel.vn/")
    return url


def load_existing_cache() -> Dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=== Parsing Goldenlife HTML ===")
    entries, province_sites = parse_goldenlife_html(HTML_PATH)
    print(f"  Extracted {len(entries)} image entries with wp-content/uploads")

    # Clean up: deduplicate site lists
    cleaned_sites = {}
    for prov, sites in province_sites.items():
        unique = list(dict.fromkeys(sites))
        filtered = [s for s in unique if len(s.strip()) > 3 and not any(
            kw in normalize(s) for kw in ['mon ngon', 'am thuc', 'dac san'])]
        if filtered:
            cleaned_sites[prov] = filtered

    total = sum(len(v) for v in cleaned_sites.values())
    print(f"  Found {len(cleaned_sites)} provinces with {total} total site listings")

    print("\n=== Loading curated sites ===")
    curated = load_curated_sites()
    print(f"  Loaded {len(curated)} curated heritage sites")

    print("\n=== Matching entries to curated sites ===")
    matched: Dict[str, Dict] = {}
    unmatched_names = []

    for entry in entries:
        site_id = match_entry_to_site(entry, curated)
        url = fix_url(entry["url"])

        if site_id:
            site_name = next((s["name"] for s in curated if s["id"] == site_id), "")

            matched[site_id] = {
                "thumb_url": url,
                "url": url,
                "title": site_name,
            }
        else:
            sn = extract_site_name_from_entry(entry)
            if sn:
                unmatched_names.append(sn)

    print(f"  Matched: {len(matched)} entries to curated sites")
    print(f"  Unmatched (with names): {len(unmatched_names)}")

    print("\n=== Sample matches ===")
    for site_id, info in list(matched.items())[:15]:
        print(f"  {info['title']:35s}")

    print("\n=== Saving wiki_images.json cache ===")
    existing = load_existing_cache()
    for site_id, entry_data in matched.items():
        existing[site_id] = entry_data

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(existing)} total entries to {CACHE_PATH}")
    print(f"  ({len(matched)} goldenlife entries added/updated)")

    print("\n=== Saving province sites to JSON ===")
    with open(PROVINCES_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned_sites, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(cleaned_sites)} provinces to {PROVINCES_JSON_PATH}")

    print(f"\n=== Done: {len(matched)} goldenlife images matched to curated sites ===")
    return len(matched)


if __name__ == "__main__":
    count = main()
    print(f"\nFinal matched count: {count}")
