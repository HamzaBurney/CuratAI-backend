"""
Image quality detection API routes for CuratAI Backend.
"""

import json
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from models.image_quality_model import (
    ErrorResponse,
    ScanHistoryResponse,
    ScanResultsResponse,
    ScanStartResponse,
)
from services.image_quality_service import ImageQualityService
from services.project_service import ProjectService
from core.logging import get_logger
from core.dependencies import get_current_user_id
from core.exceptions import DatabaseException

logger = get_logger(__name__)
router = APIRouter(prefix="/image_quality", tags=["Image Quality"])

VALID_SENSITIVITIES = {"conservative", "normal", "strict"}


def get_image_quality_service() -> ImageQualityService:
    """Dependency to get image quality service instance."""
    return ImageQualityService()


def get_project_service() -> ProjectService:
    """Dependency to get project service instance."""
    return ProjectService()


# ─── Start Scan ───────────────────────────────────────────────────────────────


@router.post(
    "/scan/start",
    response_model=ScanStartResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Project not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Start Image Quality Scan",
    description="Upload images and start a background quality scan for a project.",
)
async def start_scan(
    background_tasks: BackgroundTasks,
    project_id: str = Form(..., description="ID of the project to scan images for"),
    sensitivity: str = Form("normal", description="Scan sensitivity: conservative, normal, or strict"),
    image_ids: str = Form(..., description="JSON array of image IDs corresponding to each file, e.g. '[\"uuid1\", \"uuid2\"]'"),
    files: List[UploadFile] = File(..., description="Image files to scan"),
    user_id: str = Depends(get_current_user_id),
    quality_service: ImageQualityService = Depends(get_image_quality_service),
    project_service: ProjectService = Depends(get_project_service),
):
    """
    Start an image quality scan.

    - **project_id**: Project this scan belongs to (required)
    - **sensitivity**: Detection threshold preset (conservative / normal / strict)
    - **image_ids**: JSON array of image IDs from the images table, one per file
    - **files**: One or more image files to analyse
    """
    try:
        # Parse image_ids
        try:
            parsed_ids = json.loads(image_ids)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "VALIDATION_ERROR", "message": "image_ids must be a valid JSON array of strings"},
            )

        if not isinstance(parsed_ids, list) or not all(isinstance(i, str) for i in parsed_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "VALIDATION_ERROR", "message": "image_ids must be a JSON array of strings"},
            )

        if len(parsed_ids) != len(files):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "VALIDATION_ERROR", "message": f"Number of image_ids ({len(parsed_ids)}) must match number of files ({len(files)})"},
            )

        # Validate sensitivity
        if sensitivity not in VALID_SENSITIVITIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "VALIDATION_ERROR", "message": f"Invalid sensitivity '{sensitivity}'. Must be one of: {', '.join(VALID_SENSITIVITIES)}"},
            )

        # Validate project exists
        if not project_service.validate_project_exists(project_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "RESOURCE_NOT_FOUND", "message": f"Project '{project_id}' not found"},
            )

        # Read file contents
        files_data = []
        for f, img_id in zip(files, parsed_ids):
            content = await f.read()
            if not content:
                logger.warning(f"Skipping empty file: {f.filename}")
                continue
            files_data.append({"filename": f.filename or "unknown", "content": content, "image_id": img_id})

        if not files_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "VALIDATION_ERROR", "message": "No valid image files provided"},
            )

        # Create job
        job_id = quality_service.create_job(user_id, project_id, len(files_data), sensitivity)

        # Kick off background scan
        background_tasks.add_task(quality_service.run_scan, job_id, files_data, sensitivity)

        logger.info(f"Scan started: job_id={job_id}, images={len(files_data)}, sensitivity={sensitivity}")
        return ScanStartResponse(job_id=job_id, total_images=len(files_data))

    except HTTPException:
        raise
    except DatabaseException as e:
        logger.error(f"Database error starting scan: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.error_code, "message": e.message},
        )
    except Exception as e:
        logger.error(f"Unexpected error starting scan: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "SCAN_START_FAILED", "message": "Failed to start image quality scan"},
        )


# ─── Scan History ─────────────────────────────────────────────────────────────


@router.get(
    "/scan/history",
    response_model=ScanHistoryResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Scan History",
    description="List completed scan jobs for the current user.",
)
async def scan_history(
    project_id: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    quality_service: ImageQualityService = Depends(get_image_quality_service),
):
    """
    List completed scan jobs.

    - **project_id**: Optionally filter by project
    """
    try:
        scans = quality_service.get_history(user_id, project_id)
        return {"scans": scans}

    except DatabaseException as e:
        logger.error(f"Database error fetching scan history: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.error_code, "message": e.message},
        )


# ─── SSE Progress Stream ─────────────────────────────────────────────────────


@router.get(
    "/scan/{job_id}/progress",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
    },
    summary="Scan Progress Stream",
    description="Server-Sent Events stream for real-time scan progress.",
)
async def scan_progress(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    quality_service: ImageQualityService = Depends(get_image_quality_service),
):
    """SSE endpoint — emits progress events as images are analysed."""
    return StreamingResponse(
        quality_service.get_job_progress(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Results ──────────────────────────────────────────────────────────────────


@router.get(
    "/scan/{job_id}/results",
    response_model=ScanResultsResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Get Scan Results",
    description="Return scan results, optionally filtered by category and/or severity.",
)
async def get_results(
    job_id: str,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    quality_service: ImageQualityService = Depends(get_image_quality_service),
):
    """
    Retrieve results for a scan job.

    - **category**: Filter by issue type (blur, noise, overexposed, underexposed, low_resolution, compression, partial_blur) or "clean"
    - **severity**: Filter by overall severity (severe, moderate, mild)
    """
    try:
        result = quality_service.get_results(job_id, category, severity)
        return result

    except DatabaseException as e:
        logger.error(f"Database error fetching results for {job_id}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": e.error_code, "message": e.message},
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching results for {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "RESULTS_FETCH_FAILED", "message": "Failed to retrieve scan results"},
        )


# ─── Delete Job ───────────────────────────────────────────────────────────────


@router.delete(
    "/scan/{job_id}",
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Delete Scan Job",
    description="Delete a scan job and all its results.",
)
async def delete_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    quality_service: ImageQualityService = Depends(get_image_quality_service),
):
    """Delete a scan job and its associated results."""
    try:
        quality_service.delete_job(job_id)
        return {"message": "Scan job deleted successfully", "job_id": job_id}

    except DatabaseException as e:
        logger.error(f"Database error deleting job {job_id}: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": e.error_code, "message": e.message},
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "JOB_DELETE_FAILED", "message": "Failed to delete scan job"},
        )
