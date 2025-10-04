"""
Main application file for CuratAI Backend.
Enhanced with proper configuration, logging, middleware, and error handling.
"""

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

# Core imports
from core.config import get_settings, validate_required_settings
from core.logging import setup_logging, get_logger
from core.database import db_manager
from core.middleware import (
    RequestLoggingMiddleware,
    ErrorHandlingMiddleware,
    SecurityHeadersMiddleware
)
from core.exceptions import CuratAIException

# API routes
from api.auth_router import router as auth_router
from api.projects_router import router as projects_router
from api.images_router import router as images_router
from api.faces_recognition_router import router as faces_recognition_router

# Initialize logger
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    
    # Startup
    logger.info("Starting CuratAI Backend application...")
    
    try:
        # Validate configuration
        settings = get_settings()
        validate_required_settings(settings)
        logger.info(f"Configuration validated - Environment: {settings.environment}")
        
        # Test database connection
        if db_manager.test_connection():
            logger.info("Database connection established successfully")
        else:
            logger.warning("Database connection test failed")
        
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down CuratAI Backend application...")
    try:
        db_manager.close()
        logger.info("Application shutdown completed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    # Get settings
    settings = get_settings()
    
    # Setup logging
    setup_logging()
    
    # Create FastAPI app
    app = FastAPI(
        title=settings.app_name,
        description="AI-powered image curation backend with enhanced architecture",
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
        debug=settings.debug
    )
    
    # Add middleware (order matters!)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(images_router)
    app.include_router(faces_recognition_router)
    
    # Root endpoint
    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint with basic application information."""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "environment": settings.environment,
            "status": "healthy"
        }
    
    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check endpoint for monitoring."""
        try:
            db_health = db_manager.health_check()
            
            return {
                "status": "healthy" if db_health["connected"] else "degraded",
                "version": settings.app_version,
                "environment": settings.environment,
                "database": db_health,
                "services": {
                    "database": "healthy" if db_health["connected"] else "unhealthy"
                }
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "error": str(e),
                    "version": settings.app_version,
                    "environment": settings.environment
                }
            )
    
    # Global exception handler for unhandled exceptions
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler for unhandled errors."""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        logger.error(
            f"[{request_id}] Unhandled exception: {str(exc)}",
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
    
    # CuratAI exception handler
    @app.exception_handler(CuratAIException)
    async def curatai_exception_handler(request: Request, exc: CuratAIException):
        """Handler for custom CuratAI exceptions."""
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        logger.error(
            f"[{request_id}] CuratAI Exception: {exc.error_code} - {exc.message}",
            extra={"details": exc.details}
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id
            }
        )
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    """Run the application directly for development."""
    settings = get_settings()
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
        access_log=True
    )