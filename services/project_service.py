import logging
from supabase import create_client, Client
from config import get_config
from utils.project_utils import validate_project_name

logger = logging.getLogger(__name__)

class ProjectService:
    def __init__(self):
        """
        Initialize Supabase client
        """
        try:
            config = get_config()
            self.supabase: Client = create_client(
                config["supabase_url"],
                config["supabase_service_role_key"]
            )
            logger.info("Supabase service initialized successfully for ProjectService")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase service: {e}")
            raise

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
            logger.info(f"Checking uniqueness of project name: {project_name} for user: {user_id}")
            response = self.supabase.table("projects").select("id").eq("project_name", project_name).eq("user_id", user_id).execute()
            return len(response.data) == 0
        except Exception as e:
            logger.error(f"Error checking project name uniqueness: {str(e)}")
            raise

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
            logger.info(f"Creating project: {project_name} for user: {user_id}")

            # Validate project name
            if not validate_project_name(project_name):
                logger.warning(f"Invalid project name: {project_name}")
                raise ValueError("Invalid project name. Only alphanumeric characters, dashes (-), and underscores (_) are allowed.")

            response = self.supabase.table("projects").insert({
                "user_id": user_id,
                "project_name": project_name,
                "image_count": 0
            }).execute()

            if not response.data:
                raise Exception("Failed to create project")

            project_id = response.data[0]["id"]
            logger.info(f"Project created successfully with ID: {project_id}")
            return project_id
        except Exception as e:
            logger.error(f"Error creating project: {str(e)}")
            raise

    def delete_project(self, project_name: str, user_id: str) -> None:
        """
        Delete a project from the projects table.

        Args:
            project_name (str): Name of the project to delete.
            user_id (str): ID of the user deleting the project.

        Raises:
            Exception: If the project could not be deleted.
        """
        try:
            logger.info(f"Deleting project: {project_name} for user: {user_id}")

            response = self.supabase.table("projects").delete().eq("project_name", project_name).eq("user_id", user_id).execute()

            if not response.data:
                raise Exception("Project not found or could not be deleted")

            logger.info(f"Project deleted successfully: {project_name}")
        except Exception as e:
            logger.error(f"Error deleting project: {str(e)}")
            raise

    def get_projects(self, user_id: str) -> list[dict]:
        """
        Retrieve all projects for a given user.

        Args:
            user_id (str): ID of the user whose projects are to be retrieved.

        Returns:
            list[dict]: List of projects with their names and IDs.
        """
        try:
            logger.info(f"Fetching projects for user: {user_id}")

            response = self.supabase.table("projects").select("id, project_name").eq("user_id", user_id).execute()

            if not response.data:
                logger.info(f"No projects found for user: {user_id}")
                return []

            logger.info(f"Projects retrieved successfully for user: {user_id}")
            return response.data
        except Exception as e:
            logger.error(f"Error fetching projects: {str(e)}")
            raise