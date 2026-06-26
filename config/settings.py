from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "Vietnam Heritage Travel Recommendation System"
    version: str = "1.0.0"
    debug: bool = True

    database_url: str = "postgresql+asyncpg://heritage:heritage123@localhost:5432/heritage_travel"
    database_sync_url: str = "postgresql+psycopg2://heritage:heritage123@localhost:5432/heritage_travel"
    redis_url: str = "redis://localhost:6379/0"

    ai_service_url: str = "http://localhost:8001"
    weather_service_url: str = "http://localhost:8002"
    osrm_base_url: str = "http://localhost:5000"

    weather_cache_ttl: int = 3600
    candidate_cache_ttl: int = 86400
    route_cache_ttl: int = 86400

    default_candidate_limit: int = 30
    max_daily_hours: int = 10
    max_solve_timeout: float = 5.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
