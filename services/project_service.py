"""
Enhanced project management service for CuratAI Backend.
"""

from typing import Tuple, Any, List
from datetime import datetime, timezone
from models.project_model import ProjectData
from services.base import BaseService
from core.exceptions import (
    ResourceNotFoundException,
    ResourceConflictException,
    DatabaseException
)


class ProjectService(BaseService):
    """Service for handling project management operations."""

    def is_project_name_unique(self, project_name: str, user_id: str) -> bool:
        """
        Check if the project name is unique for the given user.

        Args:
            project_name (str): Name of the project.
            user_id (str): ID of the user.

        Returns:
            bool: True if unique, False otherwise.
        """
        try:
            self.logger.info(f"Checking uniqueness of project name: {project_name} for user: {user_id}")
            response = self.db.table("projects").select("id").eq("project_name", project_name).eq("user_id", user_id).execute()
            return len(response.data) == 0
        except Exception as e:
            self.logger.error(f"Error checking project name uniqueness: {str(e)}")
            raise DatabaseException(f"Failed to check project name uniqueness: {str(e)}")

    def create_project(self, project_name: str, user_id: str) -> str:
        """
        Create a new project in the projects table.

        Args:
            project_name (str): Name of the project.
            user_id (str): ID of the user creating the project.

        Returns:
            str: ID of the newly created project.
        """
        try:
            self.logger.info(f"Creating project: {project_name} for user: {user_id}")

            # Check if project name already exists for this user
            if not self.is_project_name_unique(project_name, user_id):
                raise ResourceConflictException(
                    f"Project name '{project_name}' already exists for this user"
                )

            # Create project record
            project_data = {
                "user_id": user_id,
                "project_name": project_name
            }

            response = self.db.table("projects").insert(project_data).execute()

            if not response.data:
                raise DatabaseException("Failed to create project")

            project_id = response.data[0]["id"]
            self.logger.info(f"Project created successfully with ID: {project_id}")
            return project_id
            
        except (ResourceConflictException, DatabaseException):
            raise
        except Exception as e:
            self.logger.error(f"Error creating project: {str(e)}")
            raise DatabaseException(f"Failed to create project: {str(e)}")

    def delete_project(self, project_id: str) -> Tuple[bool, dict]:
        """
        Delete a project from the projects table.

        Args:
            project_id (str): ID of the project to delete.

        Returns:
            Tuple of (success, result)
        """
        try:
            self.logger.info(f"Deleting project with ID: {project_id}")
            
            # First check if project exists
            project_check = self.db.table("projects").select("id").eq("id", project_id).execute()
            if not project_check.data:
                raise ResourceNotFoundException("Project", project_id)
            
            # Delete the project
            response = self.db.table("projects").delete().eq("id", project_id).execute()

            if not response:
                raise DatabaseException("Failed to delete project")

            self.logger.info(f"Project deleted successfully: {project_id}")
            
            return True, {"message": "Project deleted successfully", "project_id": project_id}
            
        except (ResourceNotFoundException, DatabaseException):
            raise
        except Exception as e:
            self.logger.error(f"Error deleting project: {str(e)}")
            raise DatabaseException(f"Failed to delete project: {str(e)}")

    def get_projects(self, user_id: str) -> List[dict]:
        """
        Retrieve all projects for a given user.

        Args:
            user_id (str): ID of the user whose projects are to be retrieved.

        Returns:
            List of projects with their details.
        """
        try:
            self.logger.info(f"Fetching projects for user: {user_id}")

            response = self.db.table("projects").select(
                "id, project_name, image_count, created_at"
            ).eq("user_id", user_id).order("created_at", desc=True).execute()

            if not response.data:
                self.logger.info(f"No projects found for user: {user_id}")
                raise ResourceNotFoundException("Projects", f"user_id: {user_id}")

            projects = []
            for project_data in response.data:
                projects.append({
                    "id": project_data["id"],
                    "project_name": project_data["project_name"],
                    "image_count": project_data.get("image_count", 0),
                    "created_at": project_data.get("created_at"),
                    "updated_at": project_data.get("updated_at")
                })

            self.logger.info(f"Retrieved {len(projects)} projects for user: {user_id}")
            return projects
            
        except Exception as e:
            self.logger.error(f"Error fetching projects: {str(e)}")
            raise DatabaseException(f"Failed to fetch projects: {str(e)}")
    
    def validate_project_exists(self, project_id: str) -> bool:
        """
        Validate that a project exists.
        
        Args:
            project_id: Project ID to validate
            
        Returns:
            True if project exists, False otherwise
        """
        try:
            response = self.db.table("projects").select("id").eq("id", project_id).execute()
            return len(response.data) > 0
        except Exception as e:
            self.logger.error(f"Error validating project existence: {e}")
            return False