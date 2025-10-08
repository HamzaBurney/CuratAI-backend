"""
Core configuration module for CuratAI Backend.
Handles environment variables, database settings, and application configuration.
"""

import os
import logging
from typing import Dict, Any, Optional
from functools import lru_cache
from enum import Enum
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Environment(str, Enum):
    """Application environment enum."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings:
    """Application settings with validation."""
    
    def __init__(self):
        # Application settings
        self.app_name: str = "CuratAI Backend"
        self.app_version: str = "1.0.0"
        self.environment: Environment = Environment(
            os.getenv("ENVIRONMENT", "development").lower()
        )
        self.debug: bool = os.getenv("DEBUG", "false").lower() == "true"
        
        # Server settings
        self.host: str = os.getenv("HOST", "0.0.0.0")
        self.port: int = int(os.getenv("PORT", "8000"))
        self.reload: bool = self.environment == Environment.DEVELOPMENT
        
        # Supabase settings
        self.supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
        self.supabase_anon_key: Optional[str] = os.getenv("SUPABASE_ANON_KEY")
        self.supabase_service_role_key: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.supabase_jwt_secret: Optional[str] = os.getenv("SUPABASE_JWT_SECRET")
        
        # Storage settings
        self.storage_bucket: str = os.getenv("STORAGE_BUCKET", "user-images")
        self.max_file_size: int = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB
        self.allowed_image_extensions: list = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
        
        # Security settings
        self.cors_origins: list = os.getenv("CORS_ORIGINS", "*").split(",")
        self.cors_allow_credentials: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
        
        # Logging settings
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_format: str = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
        self.log_file: Optional[str] = os.getenv("LOG_FILE")
        
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level not in valid_levels:
            self.log_level = "INFO"
        
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def validate_required_settings(settings: Settings) -> None:
    """Validate that all required settings are present."""
    required_fields = [
        ("supabase_url", "SUPABASE_URL"),
        ("supabase_service_role_key", "SUPABASE_SERVICE_ROLE_KEY"),
        ("supabase_jwt_secret", "SUPABASE_JWT_SECRET"),
        ("openai_api_key", "OPENAI_API_KEY")
    ]
    
    missing_fields = []
    for field_name, env_var in required_fields:
        if not getattr(settings, field_name):
            missing_fields.append(env_var)
    
    if missing_fields:
        error_msg = f"Missing required environment variables: {', '.join(missing_fields)}"
        if settings.environment == Environment.PRODUCTION:
            raise ValueError(error_msg)
        else:
            logging.warning(error_msg)


def get_database_config() -> Dict[str, Any]:
    """Get database configuration dictionary."""
    settings = get_settings()
    validate_required_settings(settings)
    
    return {
        "url": settings.supabase_url,
        "anon_key": settings.supabase_anon_key,
        "service_role_key": settings.supabase_service_role_key,
        "jwt_secret": settings.supabase_jwt_secret,
        "openai_api_key": settings.openai_api_key
    }