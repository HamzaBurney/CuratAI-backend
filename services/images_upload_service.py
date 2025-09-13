import logging
from typing import List, Dict, Optional, Tuple, Any
from supabase import create_client, Client
from config import get_config
import uuid

logger = logging.getLogger(__name__)

class ImagesUploadService:
    """Service for Supabase database operations"""
    def __init__(self):
        """Initialize Supabase client"""
        try:
            config = get_config()
            self.supabase: Client = create_client(
                config["supabase_url"],
                config["supabase_service_role_key"]
            )
            logger.info("Supabase service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase service: {e}")
            raise
    
    def test_connection(self) -> bool:
        """
        Test connection to Supabase
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            result = self.supabase.table("users").select("id").limit(1).execute()
            logger.info("Supabase connection test successful")
            return True
        except Exception as e:
            logger.error(f"Supabase connection test failed: {e}")
            return False
        
    def validate_project(self, project_id: str) -> Tuple[bool, Any]:
        try:
            result = self.supabase.table("projects").select("id").eq("id", project_id).execute()
            if result.data:
                return True, {
                    "message": "Project exists",
                    "project_id": project_id
                }
            else:
                return False, {
                    "error": "not_found",
                    "message": f"Project with ID {project_id} does not exist",
                    "project_id": project_id
                }
        except Exception as e:
            logger.error(f"Failed to validate project ID {project_id}: {e}")
            return False, {
                "error": "validation_failed",
                "message": f"Project does not exist: " + str(e),
                "project_id": project_id
            }

    def update_images_table(self, project_id: str, uploaded_images: List[Dict]) -> Tuple[bool, Any]:
        """
        Update images table with new image URLs for a given project ID
        
        Args:
            project_id (str): ID of the project
            image_urls (List[str]): List of image URLs to add
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            # rows = [{"image_url": url, "project_id": project_id} for url in image_url]
            self.supabase.table("images").insert(uploaded_images).execute()
            logger.info(f"Images table updated successfully for project_id: {project_id}")
            return True, {"message": "Images table updated successfully", 
                          "project_id": project_id,
                          "uploaded_count": len(uploaded_images)}
            
        except Exception as e:
            logger.error(f"Failed to update images table: {e}")
            return False, {"error": "update_failed", 
                           "message": "Failed to update images table: " + str(e),
                            "project_id": project_id}
    
    def upload_image_to_storage(self,project_id: str, file_name: str, image, bucket: str) -> Tuple[bool, Any]:
        """
        Upload image to Supabase storage and return public URL

        Args:
            project_id (str): ID of the project
            file_name (str): Name of the file to be stored
            image (bytes): Image file bytes
            bucket (str): Storage bucket name
            
        Returns:
            Public URL of the uploaded file if successful, None otherwise
        """
        
        try:
            
            unique_name = f"{project_id}/images/{file_name}"

            self.supabase.storage.from_(bucket).upload(unique_name, image)
            public_url = self.supabase.storage.from_(bucket).get_public_url(unique_name)
            
            logger.info(f"Image uploaded successfully: {unique_name}")
            
            return True, {
                "message": "Image uploaded successfully",
                "image_url": public_url,
                "project_id": project_id
            }
            
            
        except Exception as e:
            logger.error(f"Failed to upload file to Supabase Storage: {e}")
            return False, {
                "error": "upload_failed", 
                "message": "Failed to upload file to storage",
                "project_id": project_id
            }
        
    def upload_image(self, project_id: str, image_file, filename: str) -> Tuple[bool, Any]:
        """
        Upload image to Supabase storage
        
        Args:
            project_id: ID of the project
            image_file: Image file bytes
            filename: Original filename of the image
            
        Returns:
            Public URL of the uploaded image or None if upload failed
        """
        try:
            
            file_extension = filename.split('.')[-1].lower() if '.' in filename else 'png'
            unique_filename = f"{uuid.uuid4()}_{project_id}.{file_extension}"
            
            success, result = self.upload_image_to_storage(project_id, unique_filename, image_file, "user-images")
            if not success:
                logger.error(f"Failed to upload image to storage{project_id}")
                return False, {
                    "error": "upload_failed", 
                    "message": "Failed to upload image to storage",
                    "project_id": project_id
                }
            
            return True, result
        except Exception as e:
            logger.error(f"Exception during image upload: {e}")
            return False, {
                "error": "exception", 
                "message": str(e),
                "project_id": project_id
            }