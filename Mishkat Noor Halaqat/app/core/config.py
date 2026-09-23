import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

@dataclass(frozen=True)
class Settings:
    app_version: str = (ROOT / "VERSION").read_text().strip()
    app_env: str = os.getenv("APP_ENV", "development").lower()
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///" + (ROOT / "data" / "halaqat.db").as_posix())
    setup_token: str = os.getenv("OWNER_SETUP_TOKEN", "")
    session_hours: int = int(os.getenv("SESSION_HOURS", "24"))
    remember_days: int = int(os.getenv("REMEMBER_DAYS", "30"))
    @property
    def secure_cookie(self):
        return self.app_env == "production"

settings = Settings()
if settings.secure_cookie and not settings.database_url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
    raise RuntimeError("Production requires persistent PostgreSQL: configure DATABASE_URL.")
