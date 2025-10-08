import zipfile
import io
from typing import List, Dict, Tuple, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends, Body, Request
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
    StorageException,
    ExternalServiceException,
    DatabaseException
)
from models.face_recogntion_model import FaceRecognitionRequest
from graph.image_searching_graph import ImageSearchingGraph

logger = get_logger(__name__)
router = APIRouter(prefix="/image_searching", tags=["Image Searching"])

router.post("/",
    summary="Image Searching Endpoint",
    description="Get the image data from the uploaded zip file for image searching",
)

def get_image_searching_graph() -> ImageSearchingGraph:
    """Dependency to get image searching graph instance."""
    return ImageSearchingGraph()

@router.post("/",
    summary="Image Searching Endpoint",
    description="Search images based on uploaded images or text query",
)
async def image_searching(
    project_id: str = Form(..., description="Project ID associated with the images"),
    search_query: str = Form(..., description="Text query for image searching"),
    image_searching_graph: ImageSearchingGraph = Depends(get_image_searching_graph)
):
    
    if search_query is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="search_query must be provided"
        )
    
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id is required"
        )
    
    try:
        
        initial_state = {
            "query_str": search_query,
            "project_id": project_id,
            "face_detection_results": None,
            "face_detection_results_combined": None,
            "search_results": None,
            "json_query_extraction": None,
            "errors": []
        }
        
        # Execute the image searching graph
        result = await image_searching_graph.graph.ainvoke(initial_state)
        
        if len(result["errors"]) > 0:
            logger.error(f"Errors occurred during image searching: {result['errors']}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"errors": result["errors"]}
            )
            
        logger.info(f"Image searching completed successfully: {result['face_detection_results_combined']}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Image searching completed successfully",
                # "data": result
            }
        )
    except ValidationException as ve:
        logger.error(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    
    