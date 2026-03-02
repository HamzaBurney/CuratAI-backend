"""
Enhanced project management API routes for CuratAI Backend.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from models.project_model import (
    ProjectCreateRequest,
    ProjectDeleteRequest,
    ProjectCreateResponse,
    ProjectDeleteResponse,
    ProjectListResponse,
    ErrorResponse
)
from services.project_service import ProjectService
from core.logging import get_logger
from core.dependencies import get_current_user, get_current_user_id
from core.exceptions import (
    ResourceNotFoundException,
    ResourceConflictException,
    DatabaseException
)

logger = get_logger(__name__)
router = APIRouter(prefix="/projects", tags=["project management"])


def get_project_service() -> ProjectService:
    """Dependency to get project service instance."""
    return ProjectService()


@router.post(
    "/",
    response_model=ProjectCreateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"},
        409: {"model": ErrorResponse, "description": "Project name already exists"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Create Project",
    description="Create a new project for the authenticated user."
)
async def create_project(
    request: ProjectCreateRequest,
    user_id: str = Depends(get_current_user_id),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    Create a new project.
    
    - **project_name**: Name of the project (1-100 chars, letters, numbers, spaces, hyphens, underscores)
    
    Note: user_id is automatically extracted from the authentication token.
    """
    try:
        logger.info(f"Project creation request: {request.project_name} for user: {user_id}")
        
        # Use the authenticated user_id from the token
        project_id = project_service.create_project(request.project_name, user_id)
        
        response = {
            "message": "Project created successfully",
            "project_id": project_id
        }
        
        logger.info(f"Project created successfully with ID: {project_id}")
        return response
        
    except ResourceConflictException as e:
        logger.warning(f"Project creation conflict: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": e.error_code, "message": e.message}
        )
    except DatabaseException as e:
        logger.error(f"Database error during project creation: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.error_code, "message": e.message}
        )
    except Exception as e:
        logger.error(f"Unexpected error in create_project endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "PROJECT_CREATION_FAILED", "message": "Failed to create project"}
        )


@router.delete(
    "/{project_id}",
    response_model=ProjectDeleteResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Delete Project",
    description="Delete an existing project by ID."
)
async def delete_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    Delete a project by ID.
    
    - **project_id**: ID of the project to delete
    """
    try:
        logger.info(f"Project deletion request for ID: {project_id}")
        
        success, result = project_service.delete_project(project_id)
        
        if not success:
            # This shouldn't happen with new exception handling, but keeping for safety
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result
            )
        
        logger.info(f"Project deleted successfully: {project_id}")
        return result
        
    except ResourceNotFoundException as e:
        logger.warning(f"Project not found for deletion: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": e.error_code, "message": e.message}
        )
    except DatabaseException as e:
        logger.error(f"Database error during project deletion: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.error_code, "message": e.message}
        )
    except Exception as e:
        logger.error(f"Unexpected error in delete_project endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "PROJECT_DELETION_FAILED", "message": "Failed to delete project"}
        )


@router.get(
    "/",
    response_model=ProjectListResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="List User Projects",
    description="Retrieve all projects for the authenticated user."
)
async def list_projects(
    user_id: str = Depends(get_current_user_id),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    Get all projects for the authenticated user.
    
    Note: user_id is automatically extracted from the authentication token.
    """
    try:
        logger.info(f"Project list request for user: {user_id}")
        
        projects = project_service.get_projects(user_id)
        
        response = {"projects": projects}
        
        logger.info(f"Retrieved {len(projects)} projects for user: {user_id}")
        return response
        
    except DatabaseException as e:
        logger.error(f"Database error during project listing: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.error_code, "message": e.message}
        )
    except Exception as e:
        logger.error(f"Unexpected error in list_projects endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "PROJECT_LIST_FAILED", "message": "Failed to retrieve projects"}
        )


@router.get(
    "/{project_id}/validate",
    responses={
        200: {"description": "Project exists"},
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Validate Project",
    description="Check if a project exists by ID."
)
async def validate_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    Validate that a project exists.
    
    - **project_id**: ID of the project to validate
    """
    try:
        logger.info(f"Project validation request for ID: {project_id}")
        
        exists = project_service.validate_project_exists(project_id)
        
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "PROJECT_NOT_FOUND", "message": f"Project with ID {project_id} not found"}
            )
        
        logger.info(f"Project validation successful: {project_id}")
        return {"message": "Project exists", "project_id": project_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in validate_project endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "PROJECT_VALIDATION_FAILED", "message": "Failed to validate project"}
        )