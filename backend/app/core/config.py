"""
core/config.py - Application-wide configuration.

Reads environment variables from .env using pydantic-settings.
All other modules import from here instead of reading os.environ directly.
"""

from pathlib import Path

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

    # AI / LLM
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",   # silently ignore unknown env vars
    )

    @property
    def upload_dir_path(self) -> Path:
        """
        Resolved absolute path to the uploads directory.

        config.py lives at: backend/app/core/config.py
        Project root is:    ../../../  (3 levels up)
        Uploads dir is:     <project_root>/data/uploads

        This works regardless of where uvicorn is started from.
        """
        project_root = Path(__file__).parent.parent.parent.parent
        path = project_root / self.upload_dir
        path.mkdir(parents=True, exist_ok=True)   # create if missing
        return path


# Single shared instance - import this everywhere
settings = Settings()