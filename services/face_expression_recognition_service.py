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
import torch
from torchvision import transforms
from collections import defaultdict
from PIL import Image

class FaceExpressionRecognitionService(BaseService):
    """Service for handling face expression recognition operations."""
    
    def __init__(self):
        """Initialize the images upload service."""
        super().__init__()
        self.settings = get_settings()
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model = torch.jit.load("models/posterv2_complete.pt", map_location=self.device)
        self.model.eval()
        
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])
        ])
        print("Model loaded successfully!\n")
        
    def get_cropped_image_from_url(self, url: str) -> Optional[np.ndarray]:
        try:
            response = requests.get(url)
            response.raise_for_status()
            
            img_array = np.frombuffer(response.content, np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            
            return image
        except Exception as e:
            self.logger.error(f"Error fetching image from URL {url}: {str(e)}")
            return None
    async def get_cropped_faces(self, project_id: str) -> Tuple[bool, Any]:
        
        try:
            # Get cropped faces from cropped_faces table based on project_id
            self.logger.info(f"Fetching cropped faces for project ID: {project_id}")
            response = self.db.table("cropped_faces").select("*").eq("project_id", project_id).execute()
            cropped_faces_data = []
            if response.data:
                
                for record in response.data:
                    record_id = record["id"]
                    image_id = record["image_id"]
                    cropped_image = self.get_cropped_image_from_url(record["cropped_image_url"])
                    
                    if cropped_image is not None:
                        cropped_faces_data.append((record_id, image_id, cropped_image))
                return True, cropped_faces_data
            else:
                self.logger.warning(f"No cropped faces found for project ID: {project_id}")
                raise ValueError("No cropped faces found for project ID: {project_id}")
        
        except Exception as e:
            self.logger.error(f"Error fetching cropped faces: {str(e)}")
            return False, {"error": "getting cropped faces failed", "message": str(e)}
        
    async def generate_expression_groups(self, project_id: str, cropped_faces_data: List[Tuple[str, str, np.ndarray]]) -> Tuple[bool, Any]:
        
        try:
            self.logger.info(f"Generating expression groups for project ID: {project_id}")
            EMOTIONS = ['Neutral', 'Happy', 'Sad', 'Surprise', 'Fear', 'Disgust', 'Anger']
            expression_groups = {}
            for emotion in EMOTIONS:
                expression_groups[emotion] = []
            
            for record_id, image_id, cropped_image in cropped_faces_data:
                
                try:
                    # Convert BGR to RGB
                    image = cv2.cvtColor(cropped_image, cv2.COLOR_BGR2RGB)
                    # Convert numpy array to PIL Image for torchvision transforms
                    pil_image = Image.fromarray(image)
                    input_tensor = self.transform(pil_image).unsqueeze(0).to(self.device)

                    with torch.no_grad():
                        output = self.model(input_tensor)
                        probs = torch.nn.functional.softmax(output, dim=1)[0]
                        predicted_idx = torch.argmax(probs).item()

                    emotion_recognized = EMOTIONS[predicted_idx]
                    expression_groups[emotion_recognized].append({"image_id": image_id, "cropped_face_id": record_id})

                except Exception as e:
                    print(f"Error processing cropped image for id: {record_id}: {e}")
                    continue
                
            return True, expression_groups
        
        except Exception as e:
            self.logger.error(f"Error generating expression groups: {str(e)}")
            return False, {"error": "generating expression groups failed", "message": str(e)}
    
    async def update_expressions_table(self, project_id, expression_groups: Dict[str, List[Dict[str, str]]]) -> Tuple[bool, Any]:
        try:
            self.logger.info("Updating expressions table with new expression groups")
            records = []
            for emotion, items in expression_groups.items():
                
                grouped = defaultdict(list)

                for item in items:
                    grouped[item['image_id']].append(item['cropped_face_id'])

                # Convert defaultdict to regular dict if you want
                grouped_dict = dict(grouped)

                record = {
                    "related_images": grouped,
                    "name": emotion,
                    "project_id": project_id
                }
                records.append(record)
                
            if records:
                self.db.table("expressions").insert(records).execute()
                
                self.logger.info(f"Successfully inserted {len(records)} records into expressions table")
                return True, {
                    "message": "Uploaded expression groups successfully",
                    "uploaded_count": len(records)
                }
            else:
                self.logger.warning("No records to insert into expressions table")
                return True, []
        
        except Exception as e:
            self.logger.error(f"Error updating expressions table: {str(e)}")
            return False, {"error": "updating expressions table failed", "message": str(e)}
    
    