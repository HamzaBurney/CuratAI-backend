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
from faster_whisper import WhisperModel
import torch
import io
import tempfile
import os
from pathlib import Path

# Automatically detect GPU
device = "cuda" if torch.cuda.is_available() else "cpu"
compute_type = "float16" if device == "cuda" else "int8"  # efficient on CPU

print(f"Loading Whisper model on {device} ({compute_type})")

model = WhisperModel("base", device=device, compute_type=compute_type)

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
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized - Invalid or missing token"}
    }
)
async def image_searching(
    project_id: str = Form(..., description="Project ID associated with the images"),
    search_query: str = Form(..., description="Text query for image searching"),
    user_id: str = Depends(get_current_user_id),
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
            "scene_results": None,
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
            
        # logger.info(f"Image searching completed successfully: {result['face_detection_results_combined']}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Image searching completed successfully",
                "result": result['search_results']
                # "data": result
            }
        )
    except ValidationException as ve:
        logger.error(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    
 
@router.post(
    "/voice-input",
    summary="Voice Input Endpoint",
    description="Process voice input for image searching",
)
async def voice_input(
    audio_file: UploadFile = File(..., description="Audio file containing the voice input"),
    user_id: str = Depends(get_current_user_id),
):
    """
    Accepts an uploaded audio file (e.g. .wav or .webm), saves it temporarily,
    transcribes using Whisper, and returns the text.
    """
    
    if not audio_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio_file must be provided",
        )

    try:
        # Save uploaded file temporarily
        suffix = Path(audio_file.filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            contents = await audio_file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        # Run transcription
        result = model.transcribe(tmp_path)
        # For openai/whisper -> result["text"]
        # For faster-whisper -> result is tuple (segments, info)
        if isinstance(result, tuple):
            segments, _ = result
            text = " ".join([seg.text for seg in segments]).strip()
        else:
            text = result.get("text", "").strip()
        
        logger.info(f"Transcription result: {text}")
        return {"transcription": text}

    except Exception as e:
        logger.exception(f"Error during voice input processing: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process voice input: {str(e)}",
        )

    finally:
        # Clean up the temp file
        try:
            if tmp_path:
                os.remove(tmp_path)
        except Exception:
            pass