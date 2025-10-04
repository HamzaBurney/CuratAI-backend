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
from deepface import DeepFace
import cv2
import numpy as np
import base64

class FaceRecognitionService(BaseService):
    """Service for handling image upload operations."""
    
    def __init__(self):
        """Initialize the images upload service."""
        super().__init__()
        self.settings = get_settings()
        
    async def get_image_id_data(self, images_data: Dict[str, Tuple[str, str]]) -> Dict[str, Tuple[bytes, str]]:
        """Get the image id corresponding to its link.

        Args:
            images_data (Dict[str, bytes]): A dictionary mapping image links to their binary data.
        
        Returns:
            Dict[str, bytes]: A dictionary mapping image ID to their corresponding image IDs.
        """    
        
        try:
            self.logger.info(f"Extracting image IDs from provided image data") 
            image_id_data = {}
            for image_link, (img_b64, file_name) in images_data.items():
                # Get the image ID from its corresponding link from supabase images table
                response = self.db.table("images").select("id").eq("image_url", image_link).execute()
                if response.data:
                    image_id = response.data[0]["id"]
                    img_binary = base64.b64decode(img_b64)
                    image_id_data[image_id] = img_binary, file_name
            
            return image_id_data
        
        except Exception as e:
            self.logger.error(f"Error processing image data : {str(e)}")
            return {}
    
    async def upload_cropped_face_to_storage(self,project_id: str, file_name: str, image_data: bytes) -> Tuple[bool, Optional[str]]:
        try:
            
            bucket = self.settings.storage_bucket
            unique_name = f"{project_id}/cropped/{file_name}"
            
            # Upload to storage
            self.db.storage.from_(bucket).upload(unique_name, image_data)
            
            # Get public URL
            public_url = self.db.storage.from_(bucket).get_public_url(unique_name)
            
            self.logger.info(f"Image uploaded successfully: {unique_name}")
            
            return True, public_url
            
        except Exception as e:
            self.logger.error(f"Failed to upload file to storage: {e}")
            return False, None
    async def generate_face_embeddings(self, project_id: str, image_id_data: Dict[str, Tuple[bytes, str]]) -> Tuple[bool, Any]:
        """Generate face embeddings for the given images.

        Args:
            image_id_data (Dict[str, bytes]): A dictionary mapping image IDs to their bytes.
        Returns:
            Tuple[bool, Any]: A tuple containing a success flag and the result or error message.
        """
        try: 
            self.logger.info(f"Generating face embeddings for {len(image_id_data)} images")
            
            records = []
            count = 1
            for image_id, (image_bytes, filename) in image_id_data.items():
                self.logger.info(f"Processing image {count}/{len(image_id_data)}: ID {image_id}")
                count += 1
                nparr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is None:
                    # decoding failed
                    self.logger.error(f"Failed to decode image for ID: {image_id}")
                    continue
                
                try:
                    faces = DeepFace.extract_faces(
                        img_path=img,
                        detector_backend="retinaface",
                        align=True,
                        enforce_detection=True   # keep strict detection
                    )
                except Exception as e:
                    self.logger.warning(f"No face detected in image ID {image_id}: {e}")
                    continue  
                
                for i, face in enumerate(faces):
                    aligned_face = face["face"]  # numpy array (aligned, cropped face)

                    # aligned_face = expand_bbox(aligned_face, scale=0.1)

                    # Ensure data type is uint8 (OpenCV requirement)
                    if aligned_face.dtype != "uint8":
                        if aligned_face.max() <= 1.0:
                            aligned_face = (aligned_face * 255).astype("uint8")
                        else:
                            aligned_face = aligned_face.astype("uint8")
                    
                    # Convert RGB → BGR (OpenCV default)
                    # aligned_face_bgr = cv2.cvtColor(aligned_face, cv2.COLOR_RGB2BGR)
                    # Generate unique filename
                    file_extension = filename.split('.')[-1].lower() if '.' in filename else 'png'
                    
                    aligned_face_bgr = cv2.cvtColor(aligned_face, cv2.COLOR_RGB2BGR)
                    success, buffer = cv2.imencode(f".{file_extension}", aligned_face_bgr)
                    if not success:
                        raise ValueError("Failed to encode face to bytes")
                    image_bytes = buffer.tobytes()
                    
                    
                    unique_filename = f"{uuid.uuid4()}_{project_id}.{file_extension}"
                    success, cropped_image_url = await self.upload_cropped_face_to_storage(project_id, unique_filename, image_bytes)
                    
                    if not success:
                        self.logger.error(f"Failed to upload cropped face for image ID: {image_id}")
                        continue
                    
                    embeddings = DeepFace.represent(
                    img_path = face["face"], 
                    model_name = "ArcFace",
                    enforce_detection = False,
                    detector_backend = "skip"
                    )
                
                    records.append({
                        "image_id": image_id,
                        "cropped_image_url": cropped_image_url,
                        "embedding": embeddings[0]["embedding"]
                    })
            return True, records
        except Exception as e:
            self.logger.error(f"Error generating face embeddings: {str(e)}")
            return False, {"error": "face_embedding_failed", "message": str(e)}
        
    async def update_cropped_faces_table(self, records: List[Dict]) -> Tuple[bool, Dict[str, Any]]:
        """
        Update cropped faces with cropped image data.
        
        Args:
            project_id: ID of the project
            uploaded_images: List of image data dictionaries
            
        Returns:
            Tuple of (success, result)
        """
        try:
            # Insert image records
            self.logger.info(f"Updating cropped faces table  with {len(records)} images")
            self.db.table("cropped_faces").insert(records).execute()
            
            self.logger.info(f"Updated cropped faces table successfully with {len(records)} images")
            
            return True, {
                "message": "Uploaded cropped faces successfully",
                "uploaded_count": len(records)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to cropped faces table: {e}")
            return False, {
                "error": "update_failed",
                "message": f"Failed to cropped faces table: {str(e)}",
            }