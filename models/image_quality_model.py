"""
Pydantic models for image quality detection functionality.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel


class ScanStartResponse(BaseModel):
    """Response model for starting a scan job."""
    job_id: str
    total_images: int


class IssueDetailModel(BaseModel):
    """Model for a single quality issue detected in an image."""
    type: str
    severity: str
    score: float
    metadata: dict = {}


class ScanResultModel(BaseModel):
    """Model for a single image's scan result."""
    image_id: str
    filename: str
    thumbnail: str
    width: int
    height: int
    file_size: int
    quality_score: float
    is_clean: bool
    overall_severity: Optional[str] = None
    patch_heatmap: Optional[List[List[float]]] = None
    issues: List[IssueDetailModel] = []


class ScanSummaryModel(BaseModel):
    """Summary statistics for a scan job."""
    total: int
    issues_count: int
    clean_count: int
    categories: Dict[str, int] = {}
    severities: Dict[str, int] = {}


class ScanResultsResponse(BaseModel):
    """Response model for scan results."""
    job_id: str
    status: str
    total_images: int
    processed_images: int
    results: List[ScanResultModel] = []
    summary: ScanSummaryModel


class ScanHistoryItem(BaseModel):
    """Model for a single scan job in the history list."""
    job_id: str
    project_id: str
    sensitivity: str
    total_images: int
    completed_at: Optional[str] = None


class ScanHistoryResponse(BaseModel):
    """Response model for scan history."""
    scans: List[ScanHistoryItem] = []


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str
    message: str
    details: Optional[dict] = None
