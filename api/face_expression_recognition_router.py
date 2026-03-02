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
from services.face_expression_recognition_service import FaceExpressionRecognitionService
from core.logging import get_logger
from core.dependencies import get_current_user_id
from core.exceptions import (
    ValidationException,
    ResourceNotFoundException,
    FileUploadException,
    StorageException
)
from models.face_recogntion_model import FaceRecognitionRequest

logger = get_logger(__name__)
router = APIRouter(prefix="/face_expression_recognition", tags=["face_expression_recognition"])

def get_face_expression_recognition_service() -> FaceExpressionRecognitionService:
    """Dependency to get face expression recognition service instance."""
    return FaceExpressionRecognitionService()

@router.post("/",
    summary="Face Expression Recognition Endpoint",
    description="Get the expression groups from cropped faces for a project",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"}
    }
)
async def face_recognition(
    project_id: str = Form(..., description="ID of the project to upload images to"),
    user_id: str = Depends(get_current_user_id),
    face_expression_recognition_service: FaceExpressionRecognitionService = Depends(get_face_expression_recognition_service)
):
    
    try:
        
        success, result = await face_expression_recognition_service.get_cropped_faces(project_id)
        logger.info(f"Result from get_cropped_faces: {result}")
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to get cropped faces from the provided image data"
            )

        
        success, result = await face_expression_recognition_service.generate_expression_groups(project_id, result)
        logger.info(f"Result from generate_expression_groups: {result}")
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result
            )

        success, response = await face_expression_recognition_service.update_expressions_table(project_id, result)
        logger.info(f"Result from update_expressions_table: {response}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Face expression recognition completed successfully",
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