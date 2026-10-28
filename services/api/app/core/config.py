"""Application settings, loaded from environment variables only.

Cost controls live here: only free providers are accepted. A paid AI, email or
storage provider cannot be configured by accident because the validators reject it.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "production"]
# rule_based needs no network or key; ollama is an optional local model runtime.
AIProvider = Literal["rule_based", "ollama"]
# "none" = in-app notifications + downloadable digest only.
EmailProvider = Literal["none"]
StorageBackend = Literal["database"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = "development"
    app_name: str = "AI Job Agent"

    database_url: str = "sqlite:///./local.db"
    db_pool_size: int = Field(default=3, ge=1, le=20)
    # Storage quota of the database plan (Neon Free: 1 GB per project); used for usage warnings.
    db_storage_limit_mb: int = Field(default=1024, ge=64)

    # Signs session cookies. Must be long and random in production.
    secret_key: str = Field(default="dev-insecure-change-me-dev-insecure-change-me", min_length=32)
    session_max_age_seconds: int = Field(default=60 * 60 * 12, ge=300)
    cookie_secure: bool | None = None  # defaults to True in production
    cookie_samesite: Literal["lax", "strict"] = "lax"

    # Required to create the single owner account when set (always required in production).
    bootstrap_token: str | None = None

    # Comma-separated in the environment (NoDecode stops pydantic-settings expecting JSON).
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000"])

    login_max_attempts: int = Field(default=5, ge=1)
    login_window_seconds: int = Field(default=15 * 60, ge=10)

    # Resume uploads are stored in PostgreSQL; keep them small to stay inside free storage.
    max_upload_bytes: int = Field(default=2 * 1024 * 1024, ge=64 * 1024, le=5 * 1024 * 1024)

    ai_provider: AIProvider = "rule_based"
    ollama_base_url: str = "http://localhost:11434"
    email_provider: EmailProvider = "none"
    storage_backend: StorageBackend = "database"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, value: str) -> str:
        # Hosted providers hand out postgres:// URLs; SQLAlchemy needs an explicit driver.
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.environment == "production":
            if "insecure" in self.secret_key:
                raise ValueError("SECRET_KEY must be set to a random value in production")
            if not self.bootstrap_token:
                raise ValueError("BOOTSTRAP_TOKEN must be set in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Use PostgreSQL in production")
        return self

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


class ConfigurationError(SystemExit):
    pass


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        # Report what is wrong without echoing any configured value: the default error text
        # includes the inputs, which would put secrets (e.g. SECRET_KEY) into hosting logs.
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'settings'}: {e['msg']}" for e in exc.errors())
        raise ConfigurationError(f"Configuration error: {problems}") from None
