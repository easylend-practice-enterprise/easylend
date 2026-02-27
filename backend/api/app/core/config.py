from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "EasyLend API"
    # Als er geen .env is, valt hij terug op je lokale docker-compose instellingen
    REDIS_URL: str = "redis://:redis_geheim_456@localhost:6379/0"
    DATABASE_URL: str = "postgresql+asyncpg://easylend:supergeheim_wachtwoord_123@localhost:5432/easylend_db"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
