from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status
import zipfile
import io
from services.supabase_services import SupabaseService
from utils.images_upload_utils import allowed_file, UploadZipImagesResponse, UploadGoogleDriveImagesRequest, UploadGoogleDriveImagesResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images-upload", tags=["images-upload"])

supabase_service = SupabaseService()


@router.post("/zip/", response_model=UploadZipImagesResponse)
async def upload_zip_images(
    project_id: str = Form(..., description="ID of the project"),
    file: UploadFile = File(..., description="Zip file containing images")
):
    """
    Upload a zip file containing images, extract and store them in Supabase storage.

    Args:
        project_id (str): ID of the project
        file (UploadFile): Uploaded zip file

    Returns:
        JSONResponse: Status message and list of uploaded image URLs
    """

    try:
        
        if not file.filename.endswith('.zip'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Only .zip files are supported"
                )

        
        logger.info(f"Received zip file: {file.filename} for project_id: {project_id}")
        
        contents = await file.read()
        zip_bytes = io.BytesIO(contents)
        
        uploaded_files = []
        
        with zipfile.ZipFile(zip_bytes, "r") as zip_ref:
            file_list = zip_ref.namelist()
            # image_files = [f for f in file_list if allowed_file(f)]
            
            if not file_list:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The zip file is empty"
                )
            
            uploaded_files = []
            
            for img_name in file_list:
                
                if not allowed_file(img_name):
                    logger.warning(f"Skipping unsupported file type: {img_name}")
                    continue
                
                with zip_ref.open(img_name) as img_file:
                    
                    img_bytes = img_file.read()
                    
                    img_url = supabase_service.upload_image(
                        project_id=project_id,
                        image_file=img_bytes,
                        filename=img_name,
                    )
                    
                    if img_url:
                        uploaded_files.append(img_url)
                        # logger.info(f"Uploaded image: {img_name} to {img_url}")
            
        
        if not uploaded_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Images could not be uploaded. Ensure the zip contains valid image files."
            )
        
        return UploadZipImagesResponse(
            project_id=project_id,
            status="success",
            uploaded_images=uploaded_files
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing zip file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )