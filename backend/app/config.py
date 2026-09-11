from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://flights:flights@localhost:5432/flights"
    schedule_weeks: int = 4
    request_delay_seconds: float = 0.25
    frontend_dir: Path = ROOT_DIR / "frontend"
    schema_path: Path = ROOT_DIR / "database" / "schema.sql"
    flightsfrom_use_fixture: bool = False
    flightsfrom_fixture_path: Path = ROOT_DIR / "backend" / "tests" / "fixtures" / "calendar_popup.html"


@lru_cache
def get_settings() -> Settings:
    return Settings()
