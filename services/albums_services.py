from typing import List, Dict, Any, Tuple, Optional
from services.base import BaseService
from core.config import get_settings
from fastapi import UploadFile
import json
import numpy as np
import cv2
from deepface import DeepFace
from sklearn.preprocessing import normalize


class AlbumsService(BaseService):
    def __init__(self):
        """Initialize the images upload service."""
        super().__init__()
        self.settings = get_settings()
        
    async def get_all_images_embeddings(self, project_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Fetch all image embeddings from the 'cropped_faces' table for a given project.

        Returns:
            (success, result)
            - success: bool
            - result: {
                "message": str,
                "data": list
            }
        """
        try:
            # --- Execute Supabase query ---
            response = self.db.table("cropped_faces") \
                .select("id, image_id, embedding") \
                .eq("project_id", project_id) \
                .execute()

            # --- Case 1: No response at all ---
            if response is None:
                raise ValueError("No response object received from Supabase")

            # --- Case 2: Check for explicit Supabase error ---
            if hasattr(response, "error") and response.error:
                error_msg = response.error.get("message", str(response.error))
                self.logger.error(f"Supabase error: {error_msg}")
                return False, {
                    "message": f"Supabase query error: {error_msg}",
                    "data": []
                }

            # --- Case 3: Extract data safely ---
            data = getattr(response, "data", None)
            if data is None:
                self.logger.error("Response contained no data field")
                return False, {
                    "message": "Invalid response format: no data field",
                    "data": []
                }

            # --- Case 4: Handle empty results ---
            if not data:
                return True, {
                    "message": "No image embeddings found for this project",
                    "data": []
                }

            # --- Process and validate embeddings ---
            processed = []
            for item in data:
                emb = item.get("embedding")

                # Parse string-encoded embeddings
                if isinstance(emb, str):
                    try:
                        emb = json.loads(emb)
                    except json.JSONDecodeError:
                        self.logger.error(f"Invalid JSON embedding for id={item.get('id')}")
                        continue

                # Validate numeric list
                if isinstance(emb, list):
                    try:
                        emb = [float(x) for x in emb]
                    except (TypeError, ValueError):
                        self.logger.error(f"Non-numeric embedding values for id={item.get('id')}")
                        continue
                else:
                    self.logger.error(f"Unexpected embedding type: {type(emb)} for id={item.get('id')}")
                    continue

                item["embedding"] = emb
                processed.append(item)

            return True, {
                "message": "Successfully fetched image embeddings",
                "data": processed
            }

        except Exception as e:
            # --- Catch all unexpected runtime or network issues ---
            self.logger.error(f"Error fetching image embeddings: {e}")
            return False, {
                "message": f"Error fetching image embeddings: {str(e)}",
                "data": []
            }

    async def generate_albums(self, image_bytes: bytes, person_name: str, project_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Generate related images using face recognition
        """
        try:
            
            success, result = await self.get_all_images_embeddings(project_id)
            if not success:
                return False,{
                    "message": f"Failed to fetch image embeddings: {result.get('message', '')}"
                }
            image_embeddings = result.get("data", [])
            
            
            self.logger.info(f"Generating related images for person: {person_name}")
            if not image_bytes:
                self.logger.error("Empty image bytes provided")
                raise ValueError("Empty image bytes provided")
            
            # Convert bytes to OpenCV image
            image_array = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            if image is None:
                self.logger.error("Failed to decode image bytes")
                raise ValueError("Failed to decode image bytes")
            
            try:
                faces = DeepFace.extract_faces(
                    img_path=image,
                    detector_backend="retinaface",
                    align=True,
                    enforce_detection=True   # keep strict detection
                )
                self.logger.info(f"Extracted {len(faces)} faces from image.")
            except Exception as e:
                self.logger.warning(f"No face detected in image: {e}")
                raise ValueError(f"No face detected in image: {e}")
                

            if len(faces) > 1:
                self.logger.warning("Multiple faces detected, using the first one.")
                raise ValueError("Multiple faces detected, please provide an image with a single face.")
                
            if len(faces) == 0:
                self.logger.error("No faces detected in the image.")
                raise ValueError("No faces detected in the image.")
                
            aligned_face = faces[0]["face"]  # numpy array (aligned, cropped face)
            
            try: 
                embeddings = DeepFace.represent(
                    img_path = aligned_face, 
                    model_name = "ArcFace",
                    enforce_detection = False,
                    detector_backend = "skip"
                )
                self.logger.info(f"Generated embeddings of shape: {np.array(embeddings[0]['embedding']).shape}")
            except Exception as e:
                self.logger.error(f"Error generating embeddings: {e}")
                raise ValueError(f"Error generating embeddings: {e}")
            
            # get list of embeddings from 512D image_embeddings and then normalize them and then compute cosine similarity
            db_embeddings = [np.array(item['embedding']) for item in image_embeddings if item.get('embedding') is not None]
            if not db_embeddings:
                self.logger.warning("No embeddings found in the database.")
                raise ValueError("No embeddings found in the database.")
            
            # Convert to a 2D NumPy array
            db_embeddings = np.vstack(db_embeddings)
            db_embeddings = normalize(db_embeddings, axis=1)
            self.logger.info(f"Loaded embeddings from database")
            query_embedding = np.array(embeddings[0]['embedding'], dtype=np.float32).reshape(1, -1)
            self.logger.info(f"Generated query embedding of shape: {query_embedding.shape}")
            query_embedding = normalize(query_embedding, axis=1)[0]
            self.logger.info(f"Normalized query embedding.")
            similarities = np.dot(db_embeddings, query_embedding)
            self.logger.info(f"Computed similarities with database embeddings.")
            threshold = 0.4
            related_indices = np.where(similarities >= threshold)[0]
            related_image_ids = [image_embeddings[i]['image_id'] for i in related_indices]
            
            return True, {
                "message": "Successfully generated related images",
                "related_image_ids": related_image_ids
            }
        
        except Exception as e:
            # self.logger.error(f"Error generating related images: {e}")
            self.logger.error(f"Error generating related images: {e}")
            return False, {
                "message": f"Error generating related images: {str(e)}"
            }
            
    async def update_albums_table(self, related_image_ids: List[str], person_name: str, project_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Update albums table with new album data.
        
        Args:
            project_id: ID of the project
            person_name: Name of the person
            related_image_ids: List of related image IDs
        
        Returns:
            (success, result)
            - success: bool
            - result: {
                "message": str,
                "album_id": str (if success)
            }
        """
        try:
            if not related_image_ids or len(related_image_ids) == 0:
                self.logger.warning("No related image IDs provided to update albums table.")
                raise ValueError("No related image IDs provided to update albums table.")
            
            album_data = {
                "project_id": project_id,
                "person_name": person_name.lower(),
                "image_group": related_image_ids
            }
            
            response =self.db.table("albums").insert(album_data).execute()
            
            return True, {
                "message": "Successfully updated albums table",
            }
            # self.db.table("images").insert(uploaded_images).execute()
        except Exception as e:
            self.logger.error(f"Failed to update albums table: {e}")
            return False, {
                "message": f"Failed to update albums table: {str(e)}"
            }
            
    async def get_albums_list(self, project_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Fetch all albums for a given project.

        Returns:
            (success, result)
            - success: bool
            - result: {
                "message": str,
                "data": list
            }
        """
        try:
            response = self.db.table("albums") \
                .select("*") \
                .eq("project_id", project_id) \
                .execute()
        
            if not response.data:
                self.logger.warning(f"No albums found for project_id: {project_id}")
                return False, {
                    "message": "No albums found for the given project ID"
                }

            self.logger.info(f"Fetched albums for project_id: {project_id}")
            return True, {
                "message": "Successfully fetched albums",
                "data": response.data
            }

        except Exception as e:
            self.logger.error(f"Error fetching albums: {e}")
            return False, {
                "message": f"Error fetching albums: {str(e)}"
            }
    
    async def get_image_links(self, image_ids: List[str]) -> Tuple[bool, Dict[str, Any]]:
        """
        Fetch public URLs for a list of image IDs.

        Returns:
            (success, result)
            - success: bool
            - result: {
                "message": str,
                "data": list
            }
        """
        try:
            if not image_ids or len(image_ids) == 0:
                self.logger.warning("No image IDs provided to fetch links.")
                raise ValueError("No image IDs provided to fetch links.")
            
            response = self.db.table("images") \
                .select("id, image_url") \
                .in_("id", image_ids) \
                .execute() 
            
            if not response.data:
                self.logger.warning("No images found for the provided IDs.")
                raise ValueError("No images found for the provided IDs.")
            
            image_links = [item["image_url"] for item in response.data if item.get("image_url")]

            return True, {
                "message": "Successfully fetched image links",
                "data": image_links
            }
        except Exception as e:
            self.logger.error(f"Error fetching image links: {e}")
            return False, {
                "message": f"Error fetching image links: {str(e)}"
            }
    
    async def get_album_images(self, album_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Fetch all images for a given album.

        Returns:
            (success, result)
            - success: bool
            - result: {
                "message": str,
                "data": list
            }
        """
        try:
            response = self.db.table("albums") \
                .select("*") \
                .eq("id", album_id) \
                .execute() 
            
            if not response.data:
                self.logger.warning(f"No album found with id: {album_id}")
                raise ValueError("No album found with the given ID")
            
            album = response.data[0]
            image_ids = album.get("image_group", [])
            if not image_ids or len(image_ids) == 0:
                self.logger.warning(f"No images found in album with id: {album_id}")
                raise ValueError("No images found in the album")
            
            success, result = await self.get_image_links(image_ids)
            
            if not success:
                return False, {
                    "message": f"Failed to fetch image links: {result.get('message', '')}"
                }
            image_links = result.get("data", [])
            return True, {
                "message": "Successfully fetched album images",
                "data": album,
                "image_links": image_links
            }
            
        except Exception as e:
            self.logger.error(f"Error fetching album images: {e}")
            return False, {
                "message": f"Error fetching album images: {str(e)}"
            }
    
    async def delete_album(self, album_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Delete an album by its ID.

        Returns:
            (success, result)
            - success: bool
            - result: {
                "message": str
            }
        """
        
        try:
            if not album_id:
                self.logger.warning("No album ID provided to delete album.")
                raise ValueError("No album ID provided to delete album.")
            
            # Check if album exists
            check_response = self.db.table("albums").select("id").eq("id", album_id).execute()
            if not check_response.data:
                self.logger.warning(f"No album found with id: {album_id}")
                raise ValueError("No album found with the given ID")
            
            # Delete the album
            delete_response = self.db.table("albums").delete().eq("id", album_id).execute()
            
            self.logger.info(f"Album deleted successfully: {album_id}")
            return True, {
                "message": "Album deleted successfully"
            }
        
        except Exception as e:
            self.logger.error(f"Error deleting album: {e}")
            return False, {
                "message": f"Error deleting album: {str(e)}"
            }