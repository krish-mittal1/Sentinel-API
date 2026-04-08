from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    AUTH_SERVICE_URL: str = "http://localhost:8001"
    USER_SERVICE_URL: str = "http://localhost:8002"

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    GATEWAY_PORT: int = 8000

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_MAX_REQUESTS: int = 100

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    DEFAULT_TENANT_SLUG: str = "default"
    TENANT_HEADER_NAME: str = "X-Tenant-Slug"

    class Config:
        env_file = ".env"

settings = Settings()
