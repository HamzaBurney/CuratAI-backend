from fastapi import APIRouter, HTTPException, status
from services.auth_service import AuthService
from utils.auth_utils import SignupRequest, LoginRequest
import logging

router = APIRouter(prefix="/auth", tags=["auth"])
supabase_service = AuthService()

logger = logging.getLogger(__name__)

@router.post("/signup")
async def signup(request: SignupRequest):
    """
    User signup endpoint
    
    Args:
        request (SignupRequest): email(str), password(str), username(str)

    Returns:
        dict: Success message and user details
    """
    
    try:
        logger.info(f"Signup attempt for email: {request.email}, username: {request.username}")
        success, result = await supabase_service.signup_user(request)
    
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result
            )
        
        logger.info(f"User signed up successfully: {result['user']['email']}")
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login")
async def login(request: LoginRequest):
    """
    User login endpoint

    Args:
        request (LoginRequest): email(str), password(str)

    Returns:
        dict: Success message, user details, access token, refresh token
    """
    try:
        logger.info(f"Login attempt for email: {request.email}") 
        success, result = await supabase_service.login_user(request)
    
        if not success:
            error_type = result.get("error")
            if error_type == "invalid_credentials":
                status_code = 401
            elif error_type == "user_deactivated":
                status_code = 403
            elif error_type == "email_not_confirmed":
                status_code = 401
            else:
                status_code = 404
            raise HTTPException(status_code=status_code, detail=result)
        
        logger.info(f"User logged in successfully: {result['user']['email']}")
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
