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