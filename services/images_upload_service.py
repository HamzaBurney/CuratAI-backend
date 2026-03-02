"""
Enhanced image upload service for CuratAI Backend.
"""

import uuid
import requests
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import urlparse
from services.base import BaseService
from core.config import get_settings
from core.exceptions import (
    StorageException,
    FileUploadException,
    ExternalServiceException
)


class ImagesUploadService(BaseService):
    """Service for handling image upload operations."""
    
    def __init__(self):
        """Initialize the images upload service."""
        super().__init__()
        self.settings = get_settings()
    
    def is_allowed_file(self, filename: str) -> bool:
        """
        Check if the file has an allowed extension.
        
        Args:
            filename: Name of the file to check
            
        Returns:
            True if file extension is allowed, False otherwise
        """
        if not filename:
            return False
        
        allowed_extensions = self.settings.allowed_image_extensions
        return any(filename.lower().endswith(ext) for ext in allowed_extensions)
    
    def validate_project(self, project_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate that a project exists.
        
        Args:
            project_id: ID of the project to validate
            
        Returns:
            Tuple of (success, result)
        """
        try:
            result = self.db.table("projects").select("id").eq("id", project_id).execute()
            
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
            self.logger.error(f"Failed to validate project ID {project_id}: {e}")
            return False, {
                "error": "validation_failed",
                "message": f"Project validation failed: {str(e)}",
                "project_id": project_id
            }
    
    def update_images_table(self, project_id: str, uploaded_images: List[Dict]) -> Tuple[bool, Dict[str, Any]]:
        """
        Update images table with new image data.
        
        Args:
            project_id: ID of the project
            uploaded_images: List of image data dictionaries
            
        Returns:
            Tuple of (success, result)
        """
        try:
            # Insert image records
            self.logger.info(f"Updating images table for project_id: {project_id} with {len(uploaded_images)} images")
            self.db.table("images").insert(uploaded_images).execute()
            
            self.logger.info(f"Images table updated successfully for project_id: {project_id}")
            
            return True, {
                "message": "Images table updated successfully",
                "project_id": project_id,
                "uploaded_count": len(uploaded_images)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to update images table: {e}")
            return False, {
                "error": "update_failed",
                "message": f"Failed to update images table: {str(e)}",
                "project_id": project_id
            }
    
    def upload_image_to_storage(self, project_id: str, file_name: str, image_data: bytes) -> Tuple[bool, Dict[str, Any]]:
        """
        Upload image to Supabase storage.
        
        Args:
            project_id: ID of the project
            file_name: Name of the file to be stored
            image_data: Image file bytes
            
        Returns:
            Tuple of (success, result)
        """
        try:
            
            bucket = self.settings.storage_bucket
            unique_name = f"{project_id}/images/{file_name}"
            
            # Upload to storage
            self.db.storage.from_(bucket).upload(unique_name, image_data)
            
            # Get public URL
            public_url = self.db.storage.from_(bucket).get_public_url(unique_name)
            
            self.logger.info(f"Image uploaded successfully: {unique_name}")
            
            return True, {
                "message": "Image uploaded successfully",
                "image_url": public_url,
                "project_id": project_id,
                "storage_path": unique_name
            }
            
        except Exception as e:
            self.logger.error(f"Failed to upload file to storage: {e}")
            return False, {
                "error": "upload_failed",
                "message": f"Failed to upload file to storage: {str(e)}",
                "project_id": project_id
            }
    
    def upload_image(self, project_id: str, image_file: bytes, filename: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Upload image to storage with validation.
        
        Args:
            project_id: ID of the project
            image_file: Image file bytes
            filename: Original filename of the image
            
        Returns:
            Tuple of (success, result)
        """
        try:
            # Validate file size
            if len(image_file) > self.settings.max_file_size:
                return False, {
                    "error": "file_too_large",
                    "message": f"File size exceeds maximum allowed size of {self.settings.max_file_size} bytes",
                    "project_id": project_id
                }
            
            # Generate unique filename
            file_extension = filename.split('.')[-1].lower() if '.' in filename else 'png'
            unique_filename = f"{uuid.uuid4()}_{project_id}.{file_extension}"
            
            # Upload to storage
            success, result = self.upload_image_to_storage(project_id, unique_filename, image_file)
            
            if not success:
                self.logger.error(f"Failed to upload image to storage for project {project_id}")
                return False, result
            
            return True, result
            
        except Exception as e:
            self.logger.error(f"Exception during image upload: {e}")
            return False, {
                "error": "exception",
                "message": str(e),
                "project_id": project_id
            }
    
    async def upload_from_url(self, project_id: str, image_url: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Upload image from URL.
        
        Args:
            project_id: ID of the project
            image_url: URL of the image to upload
            
        Returns:
            Tuple of (success, result)
        """
        try:
            # Validate URL
            parsed_url = urlparse(image_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                return False, {
                    "error": "invalid_url",
                    "message": "Invalid URL format",
                    "project_id": project_id
                }
            
            # Download image
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                return False, {
                    "error": "invalid_content_type",
                    "message": "URL does not point to an image",
                    "project_id": project_id
                }
            
            # Extract filename from URL or generate one
            filename = parsed_url.path.split('/')[-1] or f"image_{uuid.uuid4().hex[:8]}.jpg"
            
            # Upload the downloaded image
            return self.upload_image(project_id, response.content, filename)
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to download image from URL {image_url}: {e}")
            return False, {
                "error": "download_failed",
                "message": f"Failed to download image from URL: {str(e)}",
                "project_id": project_id
            }
        except Exception as e:
            self.logger.error(f"Exception during URL upload: {e}")
            return False, {
                "error": "exception",
                "message": str(e),
                "project_id": project_id
            }
    
    def get_project_images(self, project_id: str) -> List[Dict[str, Any]]:
        """
        Get all images for a project.
        
        Args:
            project_id: ID of the project
            
        Returns:
            List of image data
        """
        try:
            result = self.db.table("images").select("*").eq("project_id", project_id).order("created_at", desc=True).execute()
            
            return result.data if result.data else []
            
        except Exception as e:
            self.logger.error(f"Failed to get project images: {e}")
            raise StorageException(f"Failed to retrieve project images: {str(e)}")
    
    def delete_image(self, project_id: str, image_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Delete an image from project.
        
        Args:
            project_id: ID of the project
            image_id: ID of the image to delete
            
        Returns:
            Tuple of (success, result)
        """
        try:
            # Get image data first
            image_result = self.db.table("images").select("*").eq("id", image_id).eq("project_id", project_id).execute()
            
            if not image_result.data:
                return False, {
                    "error": "not_found",
                    "message": "Image not found",
                    "project_id": project_id
                }
            
            image_data = image_result.data[0]
            
            # Delete from storage if storage path exists
            if "storage_path" in image_data:
                try:
                    self.db.storage.from_(self.settings.storage_bucket).remove([image_data["storage_path"]])
                except Exception as e:
                    self.logger.warning(f"Failed to delete from storage: {e}")
            
            # Delete from database
            self.db.table("images").delete().eq("id", image_id).execute()
            
            # Update project image count
            self.db.table("projects").update({
                "image_count": self.db.table("projects").select("image_count").eq("id", project_id).execute().data[0]["image_count"] - 1
            }).eq("id", project_id).execute()
            
            self.logger.info(f"Image deleted successfully: {image_id}")
            
            return True, {
                "message": "Image deleted successfully",
                "image_id": image_id,
                "project_id": project_id
            }
            
        except Exception as e:
            self.logger.error(f"Failed to delete image: {e}")
            return False, {
                "error": "delete_failed",
                "message": f"Failed to delete image: {str(e)}",
                "project_id": project_id
            }