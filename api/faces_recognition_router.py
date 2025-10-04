import zipfile
import io
from typing import List, Dict, Tuple
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends, Body
from fastapi.responses import JSONResponse
from models.images_model import (
    ZipUploadResponse,
    ErrorResponse
)
from services.images_upload_service import ImagesUploadService
from services.project_service import ProjectService
from services.face_recognition_service import FaceRecognitionService
from core.logging import get_logger
from core.exceptions import (
    ValidationException,
    ResourceNotFoundException,
    FileUploadException,
    StorageException
)
from models.face_recogntion_model import FaceRecognitionRequest

logger = get_logger(__name__)
router = APIRouter(prefix="/face_recognition", tags=["face recognition"])

def get_face_recognition_service() -> FaceRecognitionService:
    """Dependency to get face recognition service instance."""
    return FaceRecognitionService()

@router.post("/",
    summary="Face Recognition Endpoint",
    description="Get the image data from the uploaded zip file for face recognition",
)
async def face_recognition(
    request: FaceRecognitionRequest,
    face_recognition_service: FaceRecognitionService = Depends(get_face_recognition_service)
):
    
    try:
        
        image_id_data = await face_recognition_service.get_image_id_data(request.images_data)
    
        if image_id_data is {}:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get image IDs from the provided image data"
            )

        success, result = await face_recognition_service.generate_face_embeddings(request.project_id, image_id_data)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result
            )

        success, response = await face_recognition_service.update_cropped_faces_table(result)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Face embeddings generated and cropped faces uploaded successfully",
                "Embeddings count": len(result),
            }
        )
    
    except HTTPException:
        raise
    except ValidationException as ve:
        logger.error(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )