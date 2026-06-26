CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS heritage_sites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    province TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    geom GEOMETRY(Point, 4326),
    categories TEXT[] DEFAULT '{}',
    description TEXT DEFAULT '',
    opening_hours TEXT DEFAULT '08:00-17:00',
    estimated_visit_minutes INTEGER DEFAULT 60,
    indoor_score REAL DEFAULT 0.5,
    outdoor_score REAL DEFAULT 0.5,
    suitable_for_children BOOLEAN DEFAULT true,
    suitable_for_elderly BOOLEAN DEFAULT true,
    ticket_price INTEGER DEFAULT 0,
    popularity_score REAL DEFAULT 0.5,
    historical_importance_score REAL DEFAULT 0.5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS restaurants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    geom GEOMETRY(Point, 4326),
    province TEXT NOT NULL,
    specialty_tags TEXT[] DEFAULT '{}',
    rating REAL DEFAULT 4.0,
    review_count INTEGER DEFAULT 0,
    price_level INTEGER DEFAULT 2,
    opening_hours TEXT DEFAULT '06:00-22:00',
    source TEXT DEFAULT 'manual',
    distance_to_nearest_heritage_m REAL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS itinerary_logs (
    id SERIAL PRIMARY KEY,
    request_json JSONB NOT NULL,
    response_json JSONB,
    total_score REAL,
    total_distance_km REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_heritage_geom ON heritage_sites USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_restaurant_geom ON restaurants USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_heritage_province ON heritage_sites (province);
CREATE INDEX IF NOT EXISTS idx_restaurant_province ON restaurants (province);
CREATE INDEX IF NOT EXISTS idx_heritage_categories ON heritage_sites USING GIN (categories);
CREATE INDEX IF NOT EXISTS idx_restaurant_specialty ON restaurants USING GIN (specialty_tags);
