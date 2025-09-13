from fastapi import APIRouter, HTTPException, status
from services.project_service import ProjectService
from utils.project_utils import validate_project_name
import logging

router = APIRouter(prefix="/project", tags=["project"])
project_service = ProjectService()

logger = logging.getLogger(__name__)

@router.post("/create")
async def create_project(project_name: str, user_id: str):
    """
    Create a new project for the user.

    Args:
        project_name (str): Name of the new project.
        user_id (str): ID of the user creating the project.

    Returns:
        dict: Success message or error message.
    """
    try:
        logger.info(f"Attempting to create project: {project_name} for user: {user_id}")

        # Validate project name
        if not validate_project_name(project_name):
            logger.warning(f"Invalid project name: {project_name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid project name. Only alphanumeric characters, dashes (-), and underscores (_) are allowed."
            )

        # Check if project name already exists
        if not project_service.is_project_name_unique(project_name, user_id):
            logger.warning(f"Project name '{project_name}' already exists for user: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project name already exists. Please choose a different name."
            )

        # Create the project
        project_id = project_service.create_project(project_name, user_id)
        logger.info(f"Project created successfully with ID: {project_id}")

        return {"message": "Project created successfully", "project_id": project_id}

    except Exception as e:
        logger.error(f"Error creating project: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create project")

@router.delete("/delete")
async def delete_project(project_name: str, user_id: str):
    """
    Delete a project for the user.

    Args:
        project_name (str): Name of the project to delete.
        user_id (str): ID of the user deleting the project.

    Returns:
        dict: Success message or error message.
    """
    try:
        logger.info(f"Attempting to delete project: {project_name} for user: {user_id}")

        # Validate project name
        if not validate_project_name(project_name):
            logger.warning(f"Invalid project name: {project_name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid project name. Only alphanumeric characters, dashes (-), and underscores (_) are allowed."
            )

        # Delete the project
        project_service.delete_project(project_name, user_id)
        logger.info(f"Project deleted successfully: {project_name}")

        return {"message": "Project deleted successfully"}

    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete project")

@router.get("/view")
async def view_projects(user_id: str):
    """
    View all projects for the user.

    Args:
        user_id (str): ID of the user whose projects are to be retrieved.

    Returns:
        dict: List of projects with their names and IDs.
    """
    try:
        logger.info(f"Fetching projects for user: {user_id}")

        # Fetch projects
        projects = project_service.get_projects(user_id)
        logger.info(f"Projects retrieved successfully for user: {user_id}")

        return {"projects": projects}

    except Exception as e:
        logger.error(f"Error fetching projects: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch projects")