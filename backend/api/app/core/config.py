from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "EasyLend API"
    # Als er geen .env is, valt hij terug op je lokale docker-compose instellingen
    REDIS_URL: str = "redis://:redis_geheim_456@localhost:6379/0"
    DATABASE_URL: str = "postgresql+asyncpg://easylend:supergeheim_wachtwoord_123@localhost:5432/easylend_db"

    # JWT Configuration (ELP-22, ELP-82)
    # Geen default waarde! De app crasht als deze niet in .env staat.
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()  # type: ignore[call-arg]
