"""
core/config.py - Application-wide configuration.

Reads environment variables from .env using pydantic-settings.
All other modules import from here instead of reading os.environ directly.
"""

from pathlib import Path
from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEV_JWT_SECRET = "datalens-dev-super-secret-jwt-key-32-chars-minimum!"


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

    # Database
    database_url: str = "sqlite:///./datalens.db"

    # Auth & Security
    google_client_id: str = ""
    jwt_secret_key: str = DEFAULT_DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # CORS Allowed Origins
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",   # silently ignore unknown env vars
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def upload_dir_path(self) -> Path:
        """
        Resolved absolute path to the uploads directory.
        Supports both absolute container paths and relative development paths.
        """
        dir_path = Path(self.upload_dir)
        if dir_path.is_absolute():
            path = dir_path
        else:
            file_path = Path(__file__).resolve()
            candidate_repo_root = file_path.parent.parent.parent.parent
            if (candidate_repo_root / "backend").exists() or (candidate_repo_root / "data").exists():
                path = candidate_repo_root / self.upload_dir
            elif Path("/app/data").exists() or (len(file_path.parts) > 1 and file_path.parts[1] == "app"):
                path = Path("/app") / self.upload_dir
            else:
                path = candidate_repo_root / self.upload_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


# Single shared instance - import this everywhere
settings = Settings()
