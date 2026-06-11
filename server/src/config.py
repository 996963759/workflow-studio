import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = "postgresql+psycopg://workflow_studio:workflow_studio_dev_password@127.0.0.1:5432/workflow_studio"


def get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


APP_ENV = get_env("APP_ENV", "development")
LOG_LEVEL = get_env("LOG_LEVEL", "INFO").upper()
DIST_DIR = ROOT_DIR / "dist"
CORS_ORIGINS = [
    origin.strip()
    for origin in get_env("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
    if origin.strip()
]
DATABASE_URL = get_env("DATABASE_URL", DEFAULT_DATABASE_URL)
if not DATABASE_URL.startswith("postgresql"):
    raise ValueError("DATABASE_URL must point to PostgreSQL.")
EXTERNAL_RAG_ENABLED = get_env("EXTERNAL_RAG_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
PAISMART_BASE_URL = get_env("PAISMART_BASE_URL", "http://127.0.0.1:8080")
PAISMART_TOKEN = os.getenv("PAISMART_TOKEN", "")
PAISMART_TIMEOUT_SECONDS = float(get_env("PAISMART_TIMEOUT_SECONDS", "12"))
MODEL_CONFIG_SECRET = get_env("MODEL_CONFIG_SECRET", "workflow-studio-local-model-config-secret")
SESSION_TTL_HOURS = int(get_env("SESSION_TTL_HOURS", "168"))
WORKSPACE_INVITATION_TTL_HOURS = int(get_env("WORKSPACE_INVITATION_TTL_HOURS", "168"))
RUN_JOB_QUEUE_BACKEND = get_env("RUN_JOB_QUEUE_BACKEND", "kafka").lower()
RUN_JOB_WORKERS = int(get_env("RUN_JOB_WORKERS", "2"))
RUN_JOB_POLL_INTERVAL_SECONDS = float(get_env("RUN_JOB_POLL_INTERVAL_SECONDS", "1.0"))
KAFKA_BOOTSTRAP_SERVERS = get_env("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
KAFKA_RUN_JOB_TOPIC = get_env("KAFKA_RUN_JOB_TOPIC", "workflow-studio-run-jobs")
KAFKA_CONSUMER_GROUP = get_env("KAFKA_CONSUMER_GROUP", "workflow-studio-workers")
KAFKA_POLL_TIMEOUT_MS = int(get_env("KAFKA_POLL_TIMEOUT_MS", "2000"))
