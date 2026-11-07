from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Settings
    PROJECT_NAME: str = "FoodLence Backend"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security & JWT
    SECRET_KEY: str = "replace_this_with_a_super_secret_key_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # PostgreSQL Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "foodlence_user"
    POSTGRES_PASSWORD: str = "foodlence_password"
    POSTGRES_DB: str = "foodlence_db"
    DATABASE_URL: str | None = None

    # Connection Pooling (Configured for up to 100 concurrent connections)
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 80
    DB_POOL_PRE_PING: bool = True
    DB_POOL_RECYCLE: int = 1800

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            # Normalize driver if necessary
            return self.DATABASE_URL
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # CORS Settings
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://10.0.2.2:8000",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed]
            except Exception:
                pass
        return v if isinstance(v, list) else []

    # NLP & Machine Learning Settings
    SPACY_MODEL: str = "en_core_web_sm"
    SIMILARITY_THRESHOLD: float = 0.75
    CONFIDENCE_THRESHOLD: float = 0.70


settings = Settings()
