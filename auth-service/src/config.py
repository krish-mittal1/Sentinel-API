from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "sentinel_db"
    POSTGRES_USER: str = "sentinel"
    POSTGRES_PASSWORD: str

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 1440 

    AUTH_SERVICE_PORT: int = 8001
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    LOGIN_WINDOW_SEC: int = 300
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SEC: int = 900
    REFRESH_TOKEN_DAYS: int = 14
    PASSWORD_RESET_TOKEN_MINUTES: int = 60
    EMAIL_VERIFICATION_TOKEN_MINUTES: int = 60
    EMAIL_DELIVERY_MODE: str = "file"
    EMAIL_FROM: str = "no-reply@sentinel.local"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = False
    EMAIL_OUTPUT_DIR: str = "./outbox"
    AUTH_DEBUG_RETURN_TOKENS: bool = False
    DEFAULT_TENANT_SLUG: str = "default"
    TENANT_HEADER_NAME: str = "X-Tenant-Slug"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    class Config:
        env_file = ".env"

settings = Settings()
