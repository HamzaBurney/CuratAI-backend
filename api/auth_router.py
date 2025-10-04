"""
Enhanced authentication API routes for CuratAI Backend.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from models.auth_model import (
    SignupRequest, 
    LoginRequest, 
    SignupResponse, 
    LoginResponse, 
    UserUIDResponse,
    ErrorResponse
)
from services.auth_service import AuthService
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


def get_auth_service() -> AuthService:
    """Dependency to get auth service instance."""
    return AuthService()


@router.post(
    "/signup",
    response_model=SignupResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error or conflict"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="User Registration",
    description="Register a new user account with email, password, and username validation."
)
async def signup(
    request: SignupRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Register a new user account.
    
    - **email**: Valid email address
    - **password**: Strong password (8+ chars, uppercase, lowercase, number, special char)
    - **username**: Unique username (3-50 chars, alphanumeric + underscore/hyphen)
    """
    try:
        logger.info(f"Signup request received for email: {request.email}")
        
        success, result = await auth_service.signup_user(request)
        
        if not success:
            error_data = result
            status_code = 400
            
            if error_data.get("error") == "email_taken":
                status_code = 409
            elif error_data.get("error") == "username_taken":
                status_code = 409
            
            raise HTTPException(
                status_code=status_code,
                detail=error_data
            )
        
        logger.info(f"User signup successful: {request.email}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in signup endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "SIGNUP_FAILED", "message": "An unexpected error occurred"}
        )


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials or unconfirmed email"},
        403: {"model": ErrorResponse, "description": "Account deactivated"},
        404: {"model": ErrorResponse, "description": "User not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="User Login",
    description="Authenticate user and return access tokens."
)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Authenticate user login.
    
    - **email**: Registered email address
    - **password**: User's password
    
    Returns user information and authentication tokens.
    """
    try:
        logger.info(f"Login request received for email: {request.email}")
        
        success, result = await auth_service.login_user(request)
        
        if not success:
            error_data = result
            status_code = 401
            
            error_type = error_data.get("error")
            if error_type == "invalid_credentials":
                status_code = 401
            elif error_type == "user_deactivated":
                status_code = 403
            elif error_type == "email_not_confirmed":
                status_code = 401
            elif error_type == "user_not_found":
                status_code = 404
            
            raise HTTPException(
                status_code=status_code,
                detail=error_data
            )
        
        logger.info(f"User login successful: {request.email}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in login endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "LOGIN_FAILED", "message": "An unexpected error occurred"}
        )


@router.get(
    "/user/uid",
    response_model=UserUIDResponse,
    responses={
        404: {"model": ErrorResponse, "description": "User not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Get User UID",
    description="Retrieve the UID of the currently authenticated user."
)
async def get_user_uid(
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Get the UID of the currently authenticated user.
    
    Requires valid authentication session.
    """
    try:
        logger.info("User UID request received")
        
        uid = await auth_service.get_user_uid()
        
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "USER_NOT_FOUND", "message": "No authenticated user found"}
            )
        
        logger.info("User UID retrieved successfully")
        return {"uid": uid}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_user_uid endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "UID_RETRIEVAL_FAILED", "message": "Failed to retrieve user UID"}
        )