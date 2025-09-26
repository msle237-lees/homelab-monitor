from dataclasses import dataclass
import os

@dataclass
class Settings:
    api_url: str = os.getenv("HOMELAB_API_URL", "http://127.0.0.1:8000")
    refresh_seconds: float = float(os.getenv("HOMELAB_REFRESH_SECONDS", "5"))

settings = Settings()