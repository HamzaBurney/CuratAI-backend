import logging
from typing import List, Dict, Optional, Any, Tuple
from supabase import create_client, Client
from config import get_config
from utils.auth_utils import SignupRequest, LoginRequest, validate_password
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class AuthService:
    """Service for Supabase authentication operations"""
    def __init__(self):
        """Initialize Supabase client"""
        try:
            config = get_config()
            self.supabase: Client = create_client(
                config["supabase_url"],
                config["supabase_service_role_key"]
            )
            logger.info("Supabase service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase service: {e}")
            raise
    async def signup_user(self, request: SignupRequest) -> Tuple[bool, Any]:
        
        logger.info(f"Validating password for user: {request.email}")
        success, message = validate_password(request.password)
        if not success:
            return False, message
        
        existing_users = self.supabase.table("users").select("username").eq("username", request.username).execute()
        existing_emails = self.supabase.table("users").select("email").eq("email", request.email).execute()
        if existing_emails.data:
            return False, {"error": "email_taken", "message": "Email already registered"}
        if existing_users.data:
            return False, {"error": "username_taken", "message": "Username already taken"}
        
        
        try:
            result = self.supabase.auth.sign_up(
                {
                    "email": request.email, 
                    "password": request.password,
                    "options": {
                        "data": {  # store username in user_metadata
                            "username": request.username
                        }
                    }
                }
            )

            if not result.user:
                return False, {"error": "signup_failed", "message": "Failed to create user account"}
            logger.info(f"User account created successfully: {result}")

            user_record = {
                    "id": result.user.id,
                    "email": request.email,
                    "password": request.password,
                    "username": request.username
                }

            logger.info(f"Inserting user record into database for user: {request.email}")
            db_response = self.supabase.table("users").insert(user_record).execute()

            if not db_response:
                self.supabase.auth.api.delete_user(result.user.id)
                logger.error(f"Failed to insert user record into database: {db_response.error.message}")
                return False, {"error": "db_insert_failed", "message": "Failed to store user details"}

            return True, {
                "message": "Signup successful. Please check your email for confirmation.",
                "user": {
                    "id": result.user.id,
                    "email": result.user.email,
                    "username": result.user.user_metadata.get("username")
                }
            }
        
        except Exception as e:
            self.supabase.auth.api.delete_user(result.user.id)
            logger.error(f"Error during user signup: {e}")
            return False, {"error": "exception", "message": str(e)}
        
    async def login_user(self, request: LoginRequest) -> Tuple[bool, Any]:
        try:
            result = self.supabase.auth.sign_in_with_password(
                {
                    "email": request.email,
                    "password": request.password
                }
            )
        
            if not result.user:
                return False, {"error": "invalid_credentials", "message": "Invalid email or password"}
            if not result.user.confirmed_at:
                return False, {"error": "email_not_confirmed", "message": "Email not confirmed. Please check your inbox."}
            
            user_query = self.supabase.table("users").select("*").eq("id", result.user.id).execute()
            if not user_query.data:
                return False, {"error": "user_not_found", "message": "User profile not found"}
            user_data = user_query.data[0]
            if user_data.get("is_active") is False:
                return False, {"error": "user_deactivated", "message": "User account is deactivated. Contact support."}
            
            last_login = self.supabase.table("users") \
                .update({"last_login": datetime.now(timezone.utc).isoformat()}) \
                .eq("id", user_data["id"]) \
                .execute()
            
            return True, {
            "message": "Login successful",
            "user": {
                "id": result.user.id,
                "email": result.user.email,
                "created_at": user_data.get("created_at"),
                "username": user_data.get("username"),
                "is_active": user_data.get("is_active"),
                "last_login": last_login.data[0].get("last_login")
                
            },
            "session": result.session.__dict__ if result.session else {},
            "access_token": result.session.access_token if result.session else "",
            "refresh_token": result.session.refresh_token if result.session else ""
        }
            
        except Exception as e:
            logger.error(f"Error during user login: {e}")
            return False, {"error": "login_failed", "message": str(e)}
                
    