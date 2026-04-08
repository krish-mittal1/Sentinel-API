from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "sentinel_db"
    POSTGRES_USER: str = "sentinel"
    POSTGRES_PASSWORD: str

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    USER_SERVICE_PORT: int = 8002
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
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
