import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SERVER_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = SERVER_DIR / "data"


def get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


APP_ENV = get_env("APP_ENV", "development")
LOG_LEVEL = get_env("LOG_LEVEL", "INFO").upper()
DATABASE_PATH = Path(get_env("WORKFLOW_STUDIO_DB", str(DATA_DIR / "workflow_studio.db")))
DIST_DIR = ROOT_DIR / "dist"
CORS_ORIGINS = [
    origin.strip()
    for origin in get_env("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
    if origin.strip()
]
