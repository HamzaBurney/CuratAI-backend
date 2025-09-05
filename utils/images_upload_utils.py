from pydantic import BaseModel

def allowed_file(filename: str) -> bool:
    allowed_extensions = {".png", ".jpg", ".jpeg"}
    return any(filename.lower().endswith(ext) for ext in allowed_extensions)

# class UploadZipImagesRequest(BaseModel):
#     """ Request model for uploading zip images """
#     project_id: str
#     file: bytes  # Expecting raw bytes of the zip file

class UploadZipImagesResponse(BaseModel):
    """ Response model for uploading zip images """
    project_id: str
    status: str
    uploaded_images: list[str] = []
    
class UploadGoogleDriveImagesRequest(BaseModel):
    """ Request model for uploading images from Google Drive """
    project_id: str
    image_urls: list[str] = []

class UploadGoogleDriveImagesResponse(BaseModel):
    """ Response model for uploading images from Google Drive """
    status: str
    added_images: list[str] = []

