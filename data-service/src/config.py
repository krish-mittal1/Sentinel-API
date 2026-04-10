from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "sentinel_db"
    POSTGRES_USER: str = "sentinel"
    POSTGRES_PASSWORD: str = "sentinel_secret_123"

    JWT_SECRET: str = "changeme"
    JWT_ALGORITHM: str = "HS256"

    DATA_SERVICE_PORT: int = 8003
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @property
    def DSN(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    class Config:
        env_file = ".env"


settings = Settings()
