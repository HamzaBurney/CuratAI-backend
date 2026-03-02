"""
Database service manager for CuratAI Backend.
Handles Supabase client initialization and connection management.
"""

from typing import Optional
from supabase import create_client, Client
from core.config import get_database_config
from core.logging import LoggerMixin
from core.exceptions import DatabaseException, ExternalServiceException


class DatabaseManager(LoggerMixin):
    """Manages database connections and operations."""
    
    _instance: Optional['DatabaseManager'] = None
    _client: Optional[Client] = None
    
    def __new__(cls) -> 'DatabaseManager':
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the database manager."""
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._client = None
    
    @property
    def client(self) -> Client:
        """Get the Supabase client instance."""
        if self._client is None:
            self._initialize_client()
        return self._client
    
    def _initialize_client(self) -> None:
        """Initialize the Supabase client."""
        try:
            config = get_database_config()
            
            if not config.get("url") or not config.get("service_role_key"):
                raise DatabaseException(
                    "Missing required database configuration",
                    operation="client_initialization"
                )
            
            self._client = create_client(
                config["url"],
                config["service_role_key"]
            )
            
            self.logger.info("Database client initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database client: {e}")
            if isinstance(e, DatabaseException):
                raise
            raise DatabaseException("Failed to initialize database client", operation="client_initialization") from e
    
    def test_connection(self) -> bool:
        """
        Test the database connection.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Simple query to test connection
            result = self.client.table("users").select("id").limit(1).execute()
            self.logger.info("Database connection test successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Database connection test failed: {e}")
            return False
    
    def health_check(self) -> dict:
        """
        Perform a health check on the database.
        
        Returns:
            Health check results
        """
        try:
            is_connected = self.test_connection()
            
            return {
                "status": "healthy" if is_connected else "unhealthy",
                "connected": is_connected,
                "client_initialized": self._client is not None
            }
            
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "client_initialized": False,
                "error": str(e)
            }
    
    def close(self) -> None:
        """Close the database connection."""
        if self._client:
            # Supabase client doesn't need explicit closing
            self._client = None
            self.logger.info("Database connection closed")


# Global database manager instance
db_manager = DatabaseManager()