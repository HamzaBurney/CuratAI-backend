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
from services.albums_services import AlbumsService
from core.logging import get_logger
from core.dependencies import get_current_user_id
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
router = APIRouter(prefix="/albums", tags=["Albums"])

def get_image_searching_graph() -> ImageSearchingGraph:
    """Dependency to get image searching graph instance."""
    return ImageSearchingGraph()

def albums_service() -> AlbumsService:
    """Dependency to get images upload service instance."""
    return AlbumsService()

@router.post("/generate-albums",
    summary="Generate Albums Endpoint",
    description="Get the image data from the uploaded images, and generate albums for a specific person",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"}
    }
)
async def generate_albums(
    person_name: str = Form(..., description="Name of the person to generate albums for"),
    image: UploadFile = File(..., description="Image of the person to process"),
    project_id: str = Form(..., description="Project ID associated with the images"),
    user_id: str = Depends(get_current_user_id),
    albums_service: AlbumsService = Depends(albums_service)
):
    
    try:
        
        if not image:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No images provided for album generation"
            )
        
        if not person_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Person name is required for album generation"
            )
            
        # read image bytes
        image_bytes = await image.read()
        success, result = await albums_service.generate_albums(image_bytes, person_name, project_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to generate albums")
            )
        
        albums = result.get("related_image_ids", [])
        
        success, result = await albums_service.update_albums_table(albums, person_name, project_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to update albums table")
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "data": albums
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
        
@router.get("/get-albums-list",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"}
    }
)
async def get_albums_list(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    albums_service: AlbumsService = Depends(albums_service)
):
    
    try:
        
        if not project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project ID is required to fetch albums"
            )
        
        success, result = await albums_service.get_albums_list(project_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to fetch albums list")
            )
        
        albums = result.get("data", [])
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "data": albums
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
        
@router.get("/get-album-images",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"}
    }
)
async def get_album_images(
    album_id: str,
    user_id: str = Depends(get_current_user_id),
    albums_service: AlbumsService = Depends(albums_service)
):
    
    try:
        
        if not album_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Album ID is required to fetch album images"
            )
        
        success, result = await albums_service.get_album_images(album_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to fetch album images")
            )
        
        images = result.get("data", [])
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "data": images,
                "image_links": result.get("image_links", [])
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
        
@router.delete("/delete-album",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"}
    }
)
async def delete_album(
    album_id: str = Body(..., embed=True, description="ID of the album to delete"),
    user_id: str = Depends(get_current_user_id),
    albums_service: AlbumsService = Depends(albums_service)
):
    
    try:
        
        if not album_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Album ID is required to delete an album"
            )
        
        success, result = await albums_service.delete_album(album_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("message", "Failed to delete album")
            )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "message": result.get("message", "Album deleted successfully")
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