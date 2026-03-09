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
    
    def save_image(self, image_id: str, project_id: str, image_bytes: bytes, file_name: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Overwrite an existing image in storage and update its record in the images table.

        The file is written back to the *same* ``storage_path`` that is already
        stored in the database so the public URL is preserved (no orphaned files).

        Args:
            image_id: ID of the image record to update.
            project_id: ID of the owning project (used for authorization checks).
            image_bytes: Raw bytes of the edited image.
            file_name: Optional new filename. When supplied the extension is used to
                       infer the MIME type; the rest is ignored (path stays the same).

        Returns:
            Tuple of (success, result)
        """
        try:
            # Fetch existing record
            result = self.db.table("images").select("*").eq("id", image_id).eq("project_id", project_id).execute()
            if not result.data:
                return False, {
                    "error": "not_found",
                    "message": "Image not found",
                    "image_id": image_id,
                    "project_id": project_id,
                }

            image_record = result.data[0]
            storage_path = image_record.get("storage_path")

            if not storage_path:
                return False, {
                    "error": "missing_storage_path",
                    "message": "Existing image record has no storage path",
                    "image_id": image_id,
                }

            bucket = self.settings.storage_bucket

            # Overwrite file at the same path
            self.db.storage.from_(bucket).update(storage_path, image_bytes)

            # Re-fetch public URL (it remains the same path, but call ensures freshness)
            public_url = self.db.storage.from_(bucket).get_public_url(storage_path)

            # Update database record
            self.db.table("images").update({
                "image_url": public_url,
                "storage_path": storage_path,
            }).eq("id", image_id).execute()

            self.logger.info(f"Image overwritten successfully: {storage_path}")

            return True, {
                "message": "Image saved successfully",
                "image_id": image_id,
                "project_id": project_id,
                "image_url": public_url,
                "storage_path": storage_path,
            }

        except Exception as e:
            self.logger.error(f"Failed to save image {image_id}: {e}")
            return False, {
                "error": "save_failed",
                "message": f"Failed to save image: {str(e)}",
                "image_id": image_id,
                "project_id": project_id,
            }

    def save_image_as_copy(self, project_id: str, image_bytes: bytes, file_name: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Upload an edited image as a brand-new record (save as copy).

        A UUID-prefixed unique filename is generated so there are no collisions
        in storage, and a new row is inserted into the ``images`` table.

        Args:
            project_id: ID of the owning project.
            image_bytes: Raw bytes of the edited image.
            file_name: Desired filename for the copy (extension is preserved).

        Returns:
            Tuple of (success, result)
        """
        try:
            # Validate file size
            if len(image_bytes) > self.settings.max_file_size:
                return False, {
                    "error": "file_too_large",
                    "message": f"File size exceeds the maximum allowed size of {self.settings.max_file_size} bytes",
                    "project_id": project_id,
                }

            file_extension = file_name.split(".")[-1].lower() if "." in file_name else "png"
            unique_filename = f"{uuid.uuid4()}_{project_id}.{file_extension}"

            # Upload to storage
            success, upload_result = self.upload_image_to_storage(project_id, unique_filename, image_bytes)
            if not success:
                return False, upload_result

            # Insert new DB record
            new_record = {
                "image_url": upload_result["image_url"],
                "project_id": project_id,
                "storage_path": upload_result["storage_path"],
            }
            insert_result = self.db.table("images").insert(new_record).execute()

            if not insert_result.data:
                # Roll back the storage upload to avoid orphaned files
                try:
                    self.db.storage.from_(self.settings.storage_bucket).remove([upload_result["storage_path"]])
                except Exception:
                    pass
                return False, {
                    "error": "db_insert_failed",
                    "message": "Failed to insert new image record into the database",
                    "project_id": project_id,
                }

            new_image_id = insert_result.data[0]["id"]
            self.logger.info(f"Image copy created successfully: {upload_result['storage_path']}")

            return True, {
                "message": "Image saved as copy successfully",
                "image_id": new_image_id,
                "project_id": project_id,
                "image_url": upload_result["image_url"],
                "storage_path": upload_result["storage_path"],
            }

        except Exception as e:
            self.logger.error(f"Failed to save image as copy for project {project_id}: {e}")
            return False, {
                "error": "save_copy_failed",
                "message": f"Failed to save image as copy: {str(e)}",
                "project_id": project_id,
            }

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
            # self.db.table("projects").update({
            #     "image_count": self.db.table("projects").select("image_count").eq("id", project_id).execute().data[0]["image_count"] - 1
            # }).eq("id", project_id).execute()
            
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