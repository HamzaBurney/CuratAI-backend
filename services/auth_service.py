"""
Enhanced authentication service for CuratAI Backend.
"""

from typing import Tuple, Any, Optional
from datetime import datetime, timezone
from models.auth import SignupRequest, LoginRequest, UserResponse
from services.base import BaseService
from core.exceptions import (
    AuthenticationException,
    ResourceConflictException,
    DatabaseException
)


class AuthService(BaseService):
    """Service for handling user authentication operations."""
    
    async def signup_user(self, request: SignupRequest) -> Tuple[bool, Any]:
        """
        Register a new user.
        
        Args:
            request: User signup request data
            
        Returns:
            Tuple of (success, result)
        """
        try:
            self.logger.info(f"Processing signup request for email: {request.email}")
            
            # Check if email already exists
            existing_email = self.db.table("users").select("email").eq("email", request.email).execute()
            if existing_email.data:
                return False, {"error": "email_taken", "message": "Email already registered"}
            
            # Check if username already exists
            existing_username = self.db.table("users").select("username").eq("username", request.username).execute()
            if existing_username.data:
                return False, {"error": "username_taken", "message": "Username already taken"}
            
            # Create user account with Supabase Auth
            auth_result = self.db.auth.sign_up({
                "email": request.email,
                "password": request.password,
                "options": {
                    "data": {
                        "username": request.username
                    }
                }
            })
            
            if not auth_result.user:
                return False, {"error": "signup_failed", "message": "Failed to create user account"}
            
            self.logger.info(f"User account created with ID: {auth_result.user.id}")
            
            # Store user profile in database
            user_record = {
                "id": auth_result.user.id,
                "email": request.email,
                "username": request.username,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            db_response = self.db.table("users").insert(user_record).execute()
            
            if not db_response.data:
                # Rollback: delete auth user if database insert fails
                try:
                    self.db.auth.api.delete_user(auth_result.user.id)
                except Exception as rollback_error:
                    self.logger.error(f"Failed to rollback user creation: {rollback_error}")
                
                return False, {"error": "db_insert_failed", "message": "Failed to store user details"}
            
            user_data = db_response.data[0]
            
            self.logger.info(f"User signup completed successfully: {request.email}")
            
            return True, {
                "message": "Signup successful. Please check your email for confirmation.",
                "user": {
                    "id": user_data["id"],
                    "email": user_data["email"],
                    "username": user_data["username"],
                    "is_active": user_data.get("is_active", True),
                    "created_at": user_data.get("created_at"),
                    "last_login": None
                }
            }
            
        except Exception as e:
            self.logger.error(f"Unexpected error during signup for {request.email}: {e}")
            return False, {"error": "signup_failed", "message": str(e)}
    
    async def login_user(self, request: LoginRequest) -> Tuple[bool, Any]:
        """
        Authenticate a user login.
        
        Args:
            request: User login request data
            
        Returns:
            Tuple of (success, result)
        """
        try:
            self.logger.info(f"Processing login request for email: {request.email}")
            
            # Authenticate with Supabase Auth
            auth_result = self.db.auth.sign_in_with_password({
                "email": request.email,
                "password": request.password
            })
            
            if not auth_result.user:
                return False, {"error": "invalid_credentials", "message": "Invalid email or password"}
            
            if not auth_result.user.confirmed_at:
                return False, {"error": "email_not_confirmed", "message": "Email not confirmed. Please check your inbox."}
            
            # Get user profile from database
            user_query = self.db.table("users").select("*").eq("id", auth_result.user.id).execute()
            
            if not user_query.data:
                return False, {"error": "user_not_found", "message": "User profile not found"}
            
            user_data = user_query.data[0]
            
            if not user_data.get("is_active", True):
                return False, {"error": "user_deactivated", "message": "User account is deactivated. Contact support."}
            
            # Update last login timestamp
            last_login = self.db.table("users").update({
                "last_login": datetime.now(timezone.utc).isoformat()
            }).eq("id", user_data["id"]).execute()
            
            self.logger.info(f"User login successful: {request.email}")
            
            return True, {
                "message": "Login successful",
                "user": {
                    "id": auth_result.user.id,
                    "email": auth_result.user.email,
                    "username": user_data.get("username"),
                    "is_active": user_data.get("is_active", True),
                    "created_at": user_data.get("created_at"),
                    "last_login": last_login.data[0].get("last_login") if last_login.data else None
                },
                "access_token": auth_result.session.access_token if auth_result.session else "",
                "refresh_token": auth_result.session.refresh_token if auth_result.session else ""
            }
            
        except Exception as e:
            self.logger.error(f"Unexpected error during login for {request.email}: {e}")
            return False, {"error": "login_failed", "message": str(e)}
    
    async def get_user_uid(self) -> Optional[str]:
        """
        Get the UID of the currently authenticated user.
        
        Returns:
            User UID if found, None otherwise
        """
        try:
            self.logger.info("Fetching authenticated user UID")
            
            user_response = self.db.auth.get_user()
            
            if not user_response or not user_response.user or not user_response.user.id:
                self.logger.warning("No authenticated user found")
                return None
            
            uid = user_response.user.id
            self.logger.info(f"Retrieved UID: {uid}")
            
            return uid
            
        except Exception as e:
            self.logger.error(f"Error fetching user UID: {e}")
            return None

