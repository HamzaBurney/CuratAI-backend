"""
Pydantic models for image upload functionality.
"""

from typing import List, Optional
from pydantic import BaseModel

class ZipUploadResponse(BaseModel):
    """Response model for zip file upload."""
    message: str
    project_id: str
    uploaded_images: List[str] = []

class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str
    message: str
    details: Optional[dict] = None