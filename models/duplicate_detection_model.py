"""
Pydantic models for duplicate detection functionality.
"""

from typing import List
from pydantic import BaseModel


class DuplicateImage(BaseModel):
    image_id: str
    image_url: str


class DuplicateGroup(BaseModel):
    group_id: int
    detection_layers: List[str]
    images: List[DuplicateImage]


class DuplicateCategory(BaseModel):
    caption: str
    groups: List[DuplicateGroup]
    total_groups: int
    total_images: int


class DuplicateDetectionResponse(BaseModel):
    project_id: str
    exact_duplicates: DuplicateCategory
    near_duplicates: DuplicateCategory
