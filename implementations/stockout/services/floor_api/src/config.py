"""
Application configuration using Pydantic settings
"""

from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Open Floor Protocol"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8787
    API_PREFIX: str = "/api/v1"

    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ofp_db"
    POSTGRES_USER: str = "ofp_user"
    POSTGRES_PASSWORD: str = ""  # Must be set via environment variable POSTGRES_PASSWORD

    @property
    def DATABASE_URL(self) -> str:
        """Construct database URL"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    @property
    def REDIS_URL(self) -> str:
        """Construct Redis URL"""
        if self.REDIS_PASSWORD:
            return (
                f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}"
                f":{self.REDIS_PORT}/{self.REDIS_DB}"
            )
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Floor Manager
    FLOOR_TIMEOUT: int = 30
    FLOOR_MAX_HOLD_TIME: int = 300
    FLOOR_QUEUE_MAX_SIZE: int = 100

    # Envelope Router
    ROUTER_MAX_RETRIES: int = 3
    ROUTER_TIMEOUT: int = 10
    ROUTER_QUEUE_SIZE: int = 1000

    # Agent Registry
    REGISTRY_CLEANUP_INTERVAL: int = 60
    REGISTRY_HEARTBEAT_TIMEOUT: int = 120
    REGISTRY_MAX_AGENTS: int = 1000

    # Security
    SECRET_KEY: str = ""  # Must be set via environment variable SECRET_KEY (required in production)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS (8501/8502 = Streamlit GUIs; SSE/EventSource needs allowed origin)
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8787",
        "http://127.0.0.1:8787",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:8502",
        "http://127.0.0.1:8502",
    ]
    CORS_CREDENTIALS: bool = True

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables (like DATABASE_URL, REDIS_URL)
    )


settings = Settings()

