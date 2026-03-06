"""
Pydantic models for image upload functionality.
"""

from typing import List, Optional
from pydantic import BaseModel

class ZipUploadResponse(BaseModel):
    """Response model for zip file upload."""
    message: str
    project_id: str
    # uploaded_images: List[str] = []
    images_data: Optional[dict] = None

class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str
    message: str
    details: Optional[dict] = None


class SaveImageRequest(BaseModel):
    """Request model for overwriting an existing image with edited data."""
    image_id: str
    project_id: str
    image_data: str  # Base64-encoded image bytes
    file_name: Optional[str] = None  # If omitted, the original filename is preserved


class SaveImageCopyRequest(BaseModel):
    """Request model for saving an edited image as a new copy."""
    project_id: str
    image_data: str  # Base64-encoded image bytes
    file_name: str   # Desired filename for the new copy (including extension)


class SaveImageResponse(BaseModel):
    """Response model for save / save-as-copy operations."""
    message: str
    image_id: str
    project_id: str
    image_url: str
    storage_path: str