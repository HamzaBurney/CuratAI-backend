"""
Custom middleware for CuratAI Backend.
"""

import time
import uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from core.logging import get_logger
from core.exceptions import CuratAIException
import jwt
from jwt import PyJWKClient, ExpiredSignatureError, InvalidTokenError
from core.config import get_database_config

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details."""
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        
        # Add request ID to request state
        request.state.request_id = request_id
        
        # Log request
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} - "
            f"Client: {client_ip} - User-Agent: {request.headers.get('user-agent', 'unknown')}"
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log response
            logger.info(
                f"[{request_id}] Response: {response.status_code} - "
                f"Processing time: {process_time:.4f}s"
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log error
            logger.error(
                f"[{request_id}] Error: {str(e)} - "
                f"Processing time: {process_time:.4f}s"
            )
            
            # Re-raise the exception to be handled by error handler
            raise


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for handling and formatting errors."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle errors and format responses."""
        try:
            return await call_next(request)
            
        except CuratAIException as e:
            # Handle custom exceptions
            request_id = getattr(request.state, 'request_id', 'unknown')
            
            logger.error(
                f"[{request_id}] CuratAI Exception: {e.error_code} - {e.message}",
                extra={"details": e.details}
            )
            
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": e.error_code,
                    "message": e.message,
                    "details": e.details,
                    "request_id": request_id
                }
            )
            
        except Exception as e:
            # Handle unexpected exceptions
            request_id = getattr(request.state, 'request_id', 'unknown')
            
            logger.error(
                f"[{request_id}] Unexpected error: {str(e)}",
                exc_info=True
            )
            
            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "request_id": request_id
                }
            )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        return response
    
# Public endpoints that do NOT require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/signup",
    "/auth/login"
}

class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware for verifying Supabase access tokens on all incoming requests."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Verify Authorization header and validate JWT."""
        
        path = request.url.path
        request_id = getattr(request.state, "request_id", "unknown")

        # Skip authentication for public endpoints
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"[{request_id}] Unauthorized: Missing or invalid Authorization header for path: {path}")
            return JSONResponse(
                {"error": "UNAUTHORIZED", "message": "Missing or invalid Authorization header"},
                status_code=401,
            )

        token = auth_header.split(" ")[1]
        logger.info(f"{token}, [{request_id}] Verifying token for path: {path}")

        try:
            # Get JWKS URL from config
            jwks_url = get_database_config().get("jwks_url")
            if not jwks_url:
                logger.error(f"[{request_id}] JWKS URL not configured")
                return JSONResponse(
                    {"error": "CONFIGURATION_ERROR", "message": "Authentication service not properly configured"},
                    status_code=500,
                )
            
            # Verify token against Supabase JWKS
            jwks_client = PyJWKClient(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],  # Supabase typically uses RS256, not ES256
                audience="authenticated",
            )

            # Store user info for downstream access
            request.state.user = payload
            request.state.user_id = payload.get("sub")  # 'sub' contains the user ID
            logger.info(f"[{request_id}] Authenticated user: {payload.get('email')} (ID: {payload.get('sub')})")

            # Continue to next middleware / endpoint
            response = await call_next(request)
            return response

        except ExpiredSignatureError:
            logger.warning(f"[{request_id}] Token expired")
            return JSONResponse({"error": "TOKEN_EXPIRED", "message": "Access token has expired"}, status_code=401)

        except InvalidTokenError as e:
            logger.warning(f"[{request_id}] Invalid token: {str(e)}")
            return JSONResponse({"error": "INVALID_TOKEN", "message": "Invalid or malformed access token"}, status_code=401)

        except Exception as e:
            logger.error(f"[{request_id}] Token verification failed: {e}", exc_info=True)
            return JSONResponse(
                {"error": "AUTHENTICATION_FAILED", "message": "Token verification failed"},
                status_code=401,
            )