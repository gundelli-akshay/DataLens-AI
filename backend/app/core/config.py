"""
core/ — Application-wide configuration.

Reads environment variables from .env using pydantic-settings.
All other modules import from here instead of reading os.environ directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object.
    Values are loaded automatically from the .env file in the backend/ directory.
    """

    # Application
    app_name: str = "DataLens AI"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # File uploads
    upload_dir: str = "data/uploads"
    max_upload_size_mb: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",   # silently ignore unknown env vars
    )


# Single shared instance — import this everywhere
settings = Settings()
