"""
Enhanced image upload API routes for CuratAI Backend.
"""

import zipfile
import io
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from models.images_model import (
    ZipUploadResponse,
    ErrorResponse
)
from services.images_upload_service import ImagesUploadService
from services.project_service import ProjectService
from core.logging import get_logger
from core.dependencies import get_current_user_id
from core.exceptions import (
    ValidationException,
    ResourceNotFoundException,
    FileUploadException,
    StorageException
)
import base64

logger = get_logger(__name__)
router = APIRouter(prefix="/images", tags=["image upload"])


def get_images_service() -> ImagesUploadService:
    """Dependency to get images upload service instance."""
    return ImagesUploadService()


def get_project_service() -> ProjectService:
    """Dependency to get project service instance."""
    return ProjectService()


@router.post(
    "/upload/zip",
    response_model=ZipUploadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file or validation error"},
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        413: {"model": ErrorResponse, "description": "File too large"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Upload Images from ZIP",
    description="Upload and extract images from a ZIP file to a specific project."
)
async def upload_zip_images(
    project_id: str = Form(..., description="ID of the project to upload images to"),
    file: UploadFile = File(..., description="ZIP file containing images"),
    user_id: str = Depends(get_current_user_id),
    images_service: ImagesUploadService = Depends(get_images_service),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    Upload images from a ZIP file.
    
    - **project_id**: ID of the project to upload images to
    - **file**: ZIP file containing image files (PNG, JPG, JPEG, WebP, GIF)
    
    Supported image formats: PNG, JPG, JPEG, WebP, GIF
    Maximum file size: 50MB (configurable)
    """
    try:
        logger.info(f"ZIP upload request for project: {project_id}, file: {file.filename}")
        
        # Validate file type
        if not file.filename or not file.filename.lower().endswith('.zip'):
            raise FileUploadException(
                "Only ZIP files are supported",
                filename=file.filename
            )
        
        # Validate project exists
        if not project_service.validate_project_exists(project_id):
            raise ResourceNotFoundException("Project", project_id)
        
        # Read file contents
        contents = await file.read()
        if len(contents) == 0:
            raise FileUploadException("Empty ZIP file provided", filename=file.filename)
        
        zip_bytes = io.BytesIO(contents)
        uploaded_images = []
        images_data = {}
        
        try:
            with zipfile.ZipFile(zip_bytes, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                
                if not file_list:
                    raise FileUploadException("ZIP file is empty", filename=file.filename)
                
                logger.info(f"Processing {len(file_list)} files from ZIP")
                
                for file_name in file_list:
                    # Skip directories and hidden files
                    if file_name.endswith('/') or file_name.startswith('.'):
                        continue
                    
                    # Check if file is an allowed image type
                    if not images_service.is_allowed_file(file_name):
                        logger.warning(f"Skipping unsupported file: {file_name}")
                        continue
                    
                    try:
                        # Extract and upload individual image
                        with zip_ref.open(file_name) as img_file:
                            img_bytes = img_file.read()
                            
                            if len(img_bytes) == 0:
                                logger.warning(f"Skipping empty file: {file_name}")
                                continue
                            
                            success, result = images_service.upload_image(
                                project_id=project_id,
                                image_file=img_bytes,
                                filename=file_name
                            )
                            logger.debug(f"Upload result for {file_name}: {success}, {result}")
                            
                            if success:
                                uploaded_images.append({
                                    "image_url": result["image_url"],
                                    "project_id": project_id,
                                })
                                
                                img_b64 = base64.b64encode(img_bytes).decode("utf-8")
                                
                                images_data[result["image_url"]] = img_b64, file_name
                            else:
                                logger.warning(f"Failed to upload {file_name}: {result.get('message', 'Unknown error')}")
                    
                    except Exception as e:
                        logger.warning(f"Error processing file {file_name}: {e}")
                        continue
        
        except zipfile.BadZipFile:
            raise FileUploadException("Invalid or corrupted ZIP file", filename=file.filename)
        
        if not uploaded_images:
            raise FileUploadException(
                "No valid images found in ZIP file. Supported formats: PNG, JPG, JPEG, WebP, GIF",
                filename=file.filename
            )
        
        # Update images table
        success, db_result = images_service.update_images_table(project_id, uploaded_images)
        
        if not success:
            # If database update fails, we should ideally clean up uploaded files
            # For now, log the error
            logger.error(f"Failed to update database after uploading images: {db_result}")
            raise StorageException("Failed to save image metadata to database")
        
        response = {
            "message": f"Successfully uploaded images",
            "project_id": project_id,
            # "uploaded_images": [img["image_url"] for img in uploaded_images]
            "images_data": images_data
        }
        
        # save images_data to a json file for testing
        logger.info(f"Uploaded {len(uploaded_images)} images to project {project_id}")
        with open(f"uploaded_images.json", "w") as f:
            import json
            json.dump(images_data, f)
        
        
        return response
        
    except (FileUploadException, ResourceNotFoundException, StorageException) as e:
        logger.error(f"Upload error: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail={"error": e.error_code, "message": e.message, "details": e.details}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in zip upload: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "UPLOAD_FAILED", "message": "An unexpected error occurred during upload"}
        )

@router.get(
    "/{project_id}",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="List Project Images",
    description="Get all images for a specific project."
)
async def list_project_images(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    images_service: ImagesUploadService = Depends(get_images_service),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    List all images for a project.
    
    - **project_id**: ID of the project to list images for
    """
    try:
        logger.info(f"List images request for project: {project_id}")
        
        # Validate project exists
        if not project_service.validate_project_exists(project_id):
            raise ResourceNotFoundException("Project", project_id)
        
        images = images_service.get_project_images(project_id)
        
        response = {
            "project_id": project_id,
            "image_count": len(images),
            "images": images
        }
        
        logger.info(f"Retrieved {len(images)} images for project {project_id}")
        return response
        
    except ResourceNotFoundException as e:
        logger.error(f"Project not found: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail={"error": e.error_code, "message": e.message}
        )
    except Exception as e:
        logger.error(f"Unexpected error in list images: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "LIST_IMAGES_FAILED", "message": "Failed to retrieve project images"}
        )


@router.delete(
    "/{project_id}/{image_id}",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"},
        404: {"model": ErrorResponse, "description": "Project or image not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Delete Project Image",
    description="Delete a specific image from a project."
)
async def delete_project_image(
    project_id: str,
    image_id: str,
    user_id: str = Depends(get_current_user_id),
    images_service: ImagesUploadService = Depends(get_images_service),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    Delete a specific image from a project.
    
    - **project_id**: ID of the project
    - **image_id**: ID of the image to delete
    """
    try:
        logger.info(f"Delete image request: project {project_id}, image {image_id}")
        
        # Validate project exists
        if not project_service.validate_project_exists(project_id):
            raise ResourceNotFoundException("Project", project_id)
        
        success, result = images_service.delete_image(project_id, image_id)
        
        if not success:
            if result.get("error") == "not_found":
                raise ResourceNotFoundException("Image", image_id)
            else:
                raise StorageException("Failed to delete image")
        
        logger.info(f"Image deleted successfully: {image_id}")
        return {"message": "Image deleted successfully", "image_id": image_id}
        
    except (ResourceNotFoundException, StorageException) as e:
        logger.error(f"Delete image error: {e.message}")
        raise HTTPException(
            status_code=e.status_code,
            detail={"error": e.error_code, "message": e.message}
        )
    except Exception as e:
        logger.error(f"Unexpected error in delete image: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "DELETE_IMAGE_FAILED", "message": "Failed to delete image"}
        )