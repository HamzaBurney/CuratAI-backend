"""
Pydantic models for user authentication and authorization.
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
import re


class SignupRequest(BaseModel):
    """Request model for user signup."""
    email: EmailStr
    password: str
    username: str
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not v or len(v.strip()) < 3:
            raise ValueError('Username must be at least 3 characters long')
        if len(v) > 50:
            raise ValueError('Username must be no more than 50 characters long')
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username can only contain letters, numbers, hyphens, and underscores')
        return v.strip()
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[@$!%*?&]', v):
            raise ValueError('Password must contain at least one special character (@, $, !, %, *, ?, &)')
        return v


class LoginRequest(BaseModel):
    """Request model for user login."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Response model for user data."""
    id: str
    email: str
    username: str
    is_active: bool = True  # Default to True if not provided
    created_at: Optional[str] = None
    last_login: Optional[str] = None


class SignupResponse(BaseModel):
    """Response model for user signup."""
    message: str
    user: UserResponse


class LoginResponse(BaseModel):
    """Response model for user login."""
    message: str
    user: UserResponse
    access_token: str
    refresh_token: str


class UserUIDResponse(BaseModel):
    """Response model for user UID."""
    uid: str


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str
    message: str
    details: Optional[dict] = None