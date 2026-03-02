"""
Pydantic models for project management.
"""

from typing import List, Optional
from pydantic import BaseModel, field_validator
import re


class ProjectCreateRequest(BaseModel):
    """Request model for creating a project."""
    project_name: str
    
    @field_validator('project_name')
    @classmethod
    def validate_project_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Project name cannot be empty')
        
        v = v.strip()
        if len(v) < 1:
            raise ValueError('Project name must be at least 1 character long')
        if len(v) > 100:
            raise ValueError('Project name must be no more than 100 characters long')
            
        # Only allow alphanumeric characters, dashes, underscores, and spaces
        if not re.match(r'^[a-zA-Z0-9_\s-]+$', v):
            raise ValueError('Project name can only contain letters, numbers, spaces, hyphens, and underscores')
        
        return v


class ProjectDeleteRequest(BaseModel):
    """Request model for deleting a project."""
    project_id: str
    
    @field_validator('project_id')
    @classmethod
    def validate_project_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Project ID cannot be empty')
        return v.strip()


class ProjectViewRequest(BaseModel):
    """Request model for viewing projects (deprecated - user_id now comes from auth token)."""
    pass


class ProjectData(BaseModel):
    """Model for project data."""
    id: str
    project_name: str
    image_count: Optional[int] = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectCreateResponse(BaseModel):
    """Response model for project creation."""
    message: str
    project_id: str


class ProjectDeleteResponse(BaseModel):
    """Response model for project deletion."""
    message: str
    project_id: str


class ProjectListResponse(BaseModel):
    """Response model for project listing."""
    projects: List[ProjectData]


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str
    message: str
    details: Optional[dict] = None