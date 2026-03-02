"""
Base service class for CuratAI Backend services.
"""

from abc import ABC
from typing import Optional
from supabase import Client
from core.database import db_manager
from core.logging import LoggerMixin


class BaseService(LoggerMixin, ABC):
    """Base service class with common functionality."""
    
    def __init__(self):
        """Initialize the base service."""
        self._db_client: Optional[Client] = None
    
    @property
    def db(self) -> Client:
        """Get the database client."""
        if self._db_client is None:
            self._db_client = db_manager.client
        return self._db_client
    
    def health_check(self) -> dict:
        """
        Perform a health check for the service.
        
        Returns:
            Health check results
        """
        try:
            # Test database connection
            db_health = db_manager.health_check()
            
            return {
                "service": self.__class__.__name__,
                "status": "healthy" if db_health["connected"] else "unhealthy",
                "database": db_health
            }
            
        except Exception as e:
            self.logger.error(f"Health check failed for {self.__class__.__name__}: {e}")
            return {
                "service": self.__class__.__name__,
                "status": "unhealthy",
                "error": str(e)
            }