from pydantic import BaseModel
from typing import Dict, Tuple

class FaceRecognitionRequest(BaseModel):
    project_id: str
    images_data: Dict[str, Tuple[str, str]]
