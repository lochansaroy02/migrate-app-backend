from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "DataBridge"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # Database (application DB)
    DATABASE_URL: str = Field(..., description="PostgreSQL URL for application metadata")
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800

    # Redis
    REDIS_URL: str = Field(..., description="Redis URL for Celery broker/backend")

    # Celery
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: list[str] = ["json"]
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_TIME_LIMIT: int = 3600 * 6  # 6 hours max per migration
    CELERY_TASK_SOFT_TIME_LIMIT: int = 3600 * 5

    # Encryption
    ENCRYPTION_KEY: str = Field(..., description="Fernet key for encrypting connection credentials")

    # Migration defaults
    DEFAULT_BATCH_SIZE: int = 1000
    MAX_BATCH_SIZE: int = 50000
    MIN_BATCH_SIZE: int = 100
    MAX_RETRY_ATTEMPTS: int = 3
    RETRY_DELAY_SECONDS: int = 5

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30

    model_config = {"env_file": ".env", "case_sensitive": True}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
