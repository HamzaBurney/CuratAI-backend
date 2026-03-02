"""
Authentication dependencies for FastAPI endpoints.
"""

from typing import Dict, Any
from fastapi import Request, HTTPException, status
from core.logging import get_logger

logger = get_logger(__name__)


async def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Dependency to get the current authenticated user from request state.
    
    This should be used in protected endpoints to access user information.
    The user data is set by the AuthenticationMiddleware.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Dict containing user payload from JWT token
        
    Raises:
        HTTPException: If user is not authenticated
        
    Example:
        ```python
        @router.get("/protected")
        async def protected_endpoint(current_user: dict = Depends(get_current_user)):
            user_id = current_user.get("sub")
            email = current_user.get("email")
            return {"message": f"Hello {email}"}
        ```
    """
    user = getattr(request.state, "user", None)
    
    if not user:
        logger.error("User not found in request state - authentication may have failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    return user


async def get_current_user_id(request: Request) -> str:
    """
    Dependency to get the current authenticated user's ID.
    
    Args:
        request: FastAPI request object
        
    Returns:
        User ID (UUID string) from JWT token
        
    Raises:
        HTTPException: If user is not authenticated
        
    Example:
        ```python
        @router.get("/my-profile")
        async def get_profile(user_id: str = Depends(get_current_user_id)):
            # Use user_id to fetch profile
            return {"user_id": user_id}
        ```
    """
    user_id = getattr(request.state, "user_id", None)
    
    if not user_id:
        logger.error("User ID not found in request state")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    return user_id
