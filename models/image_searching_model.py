from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
from fastapi import UploadFile
import operator

class ImageSearchingState(TypedDict):
    
    people_names: Optional[List[str]]
    query_str:  Optional[str]
    project_id: str
    
    face_detection_results: Optional[List[Dict[str, Any]]]
    face_detection_results_combined: Optional[Dict[str, Any]]
    scene_results: Optional[Dict[str, Any]]
    search_results: Optional[Dict[str, Any]]
    
    json_query_extraction: Optional[Dict[str, Any]]
    
    errors: Annotated[List[str], operator.add]
    
class SearchResult(BaseModel):
    people: List[str] = Field(..., description="List of person names")
    emotions: List[str] = Field(..., description="List of emotional states or facial expressions")
    scene: str = Field(..., description="Description of the environment or background")
    errors: List[str] = Field(..., description="List of any errors encountered")

