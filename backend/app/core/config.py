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
    Values are loaded automatically from the .env file in the backend/ directory or container env.
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

    # Persistent Object Storage (Supabase Storage is the exclusive file storage backend)
    supabase_url: str = ""
    supabase_key: str = ""  # Service-role or secret key; backend only, never exposed to clients
    supabase_storage_bucket: str = "datalens-files"
    storage_backend: str = "supabase"

    # AI / LLM (Primary: Gemini 3.8 Flash, Secondary/Fallback: Groq)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com"

    # Database (PostgreSQL is the exclusive database backend; must be explicitly configured)
    database_url: str = ""

    # Auth & Security
    google_client_id: str = ""
    jwt_secret_key: str = DEFAULT_DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # CORS Allowed Origins
    cors_origins: Union[List[str], str] = [
        "https://data-lens-ai-beta.vercel.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    @field_validator("groq_base_url", mode="before")
    @classmethod
    def normalize_groq_base_url(cls, v: Union[str, None]) -> str:
        if not v or not isinstance(v, str):
            return "https://api.groq.com"
        clean = v.strip().rstrip("/")
        if clean.endswith("/openai/v1"):
            clean = clean[:-len("/openai/v1")]
        return clean or "https://api.groq.com"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            origins = [
                origin.strip().strip("\"'").rstrip("/")
                for origin in v.split(",")
                if origin.strip()
            ]
        elif isinstance(v, list):
            origins = [
                str(origin).strip().strip("\"'").rstrip("/")
                for origin in v
                if str(origin).strip()
            ]
        else:
            origins = [
                "https://data-lens-ai-beta.vercel.app",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ]

        # Always ensure production Vercel frontend is included if not already present
        prod_origin = "https://data-lens-ai-beta.vercel.app"
        if prod_origin not in origins and "*" not in origins:
            origins.append(prod_origin)

        return origins

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",   # silently ignore unknown env vars
    )

    @property
    def is_gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.strip())

    @property
    def is_supabase_storage_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_url.strip() and self.supabase_key and self.supabase_key.strip())

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    def validate_production_errors(self) -> List[str]:
        """
        Return fatal configuration errors for production deployments.
        In production (APP_ENV=production):
        1. DATABASE_URL must be PostgreSQL (SQLite is not permitted in production).
        2. Persistent object storage (Supabase Storage) must be configured (local fallback is not permitted).
        3. JWT_SECRET_KEY must not be the default development secret and must be >= 32 chars.
        4. CORS_ORIGINS must not contain wildcard '*'.
        """
        errors: List[str] = []
        if self.is_production:
            # 1. Database requirement: PostgreSQL only (SQLite is not permitted)
            db_clean = (self.database_url or "").strip().lower()
            if not db_clean or db_clean.startswith("sqlite") or not db_clean.startswith(("postgresql://", "postgres://")):
                errors.append(
                    "DATABASE_URL must be configured with a PostgreSQL connection string (SQLite is not permitted)."
                )

            # 2. Storage requirement: Supabase Storage only (local fallback is not permitted)
            if not self.is_supabase_storage_enabled:
                errors.append(
                    "Persistent object storage (Supabase Storage) must be configured via SUPABASE_URL and SUPABASE_KEY. Local storage fallback is not permitted."
                )

            # 3. JWT Secret requirement
            if self.jwt_secret_key == DEFAULT_DEV_JWT_SECRET or len(self.jwt_secret_key) < 32:
                errors.append(
                    "JWT_SECRET_KEY is using an insecure default or is shorter than 32 characters."
                )

            # 4. CORS requirement: No wildcard in production
            if any(origin == "*" for origin in self.cors_origins):
                errors.append(
                    "CORS_ORIGINS contains wildcard '*' which is forbidden in production."
                )

        return errors

    def validate_production_settings(self) -> List[str]:
        """
        Return all production validation errors and warnings.
        """
        messages = self.validate_production_errors()
        if self.is_production:
            if not self.groq_api_key or not self.groq_api_key.strip():
                messages.append(
                    "GROQ_API_KEY is not set in production mode. AI Insights and Document RAG chat will be unavailable."
                )
        return messages

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
