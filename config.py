import os
from dotenv import load_dotenv
from typing import Dict, Any
import warnings

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")

ENV_VALIDATION_ERRORS = []

if not SUPABASE_URL:
    ENV_VALIDATION_ERRORS.append("SUPABASE_URL environment variable is required but not set")
if not SUPABASE_ANON_KEY:
    ENV_VALIDATION_ERRORS.append("SUPABASE_ANON_KEY environment variable is required but not set")
if not SUPABASE_SERVICE_ROLE_KEY:
    ENV_VALIDATION_ERRORS.append("SUPABASE_SERVICE_ROLE_KEY environment variable is required but not set")
if not SUPABASE_JWT_SECRET:
    ENV_VALIDATION_ERRORS.append("SUPABASE_JWT_SECRET environment variable is required but not set")
    
def validate_environment():
    """Log missing environment variables as warnings, do not raise errors."""
    if ENV_VALIDATION_ERRORS:
        warning_message = "Missing required environment variables:\n" + "\n".join(f"- {error}" for error in ENV_VALIDATION_ERRORS)
        warnings.warn(warning_message)
        
def get_config() -> Dict[str, Any]:
    """Get configuration dictionary."""
    validate_environment() 
    
    return {
        "supabase_url": SUPABASE_URL,
        "supabase_anon_key": SUPABASE_ANON_KEY,
        "supabase_service_role_key": SUPABASE_SERVICE_ROLE_KEY,
        "supabase_jwt_secret": SUPABASE_JWT_SECRET,
}