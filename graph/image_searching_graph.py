from typing import List, Dict, Tuple, Optional
from fastapi import UploadFile
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from models.image_searching_model import ImageSearchingState, SearchResult
from core.config import get_settings
from services.image_searching_service import ImageSearchingService
import logging
import asyncio

logger = logging.getLogger(__name__)

def get_image_searching_service() -> ImageSearchingService:
    """Dependency to get image searching service instance."""
    return ImageSearchingService()

class ImageSearchingGraph:
    def __init__(self):
        
        self.settings = get_settings()
        self.llm = ChatOpenAI(
            model="openai/gpt-oss-20b:free",
            base_url = "https://openrouter.ai/api/v1",
            temperature=0.5,
            api_key= self.settings.openai_api_key
        )
        self.graph = self._build_graph()
        self.image_searching_service = get_image_searching_service()

        logger.info("ImageSearchingGraph initialized successfully")
    
    async def _get_people_names_from_supabase_node(self, state: ImageSearchingState) -> ImageSearchingState:
        
        try:

            logger.info(f"[_get_people_names_from_supabase_node] Fetching people names in the available albums for project_id: {state['project_id']}")
            success, result = await self.image_searching_service.get_people_names_from_supabase(state["project_id"])
            if success:
                state["people_names"] = result["people_names"]
                logger.info(f"Fetched {len(result)} people names from Supabase")
            else:
                state["people_names"] = []
                raise ValueError(result["error"])
            return state
        
        except Exception as e:
            logger.error(f"Error in _get_people_names_from_supabase_node: {str(e)}")
            self.add_error(state, f"Error in _get_people_names_from_supabase_node: {str(e)}")
            # state["errors"].extend(errors if isinstance(errors, list) else [errors])
            return state
    
    async def _get_data_from_search_query_node(self, state: ImageSearchingState) -> ImageSearchingState:
        
        try:
            
            logger.info(f"[_get_data_from_search_query_node] Processing search query: {state['query_str']}")
            if state["query_str"]:
                # Use LLM to process the query string and extract relevant information
                search_prompt = self.image_searching_service.get_search_prompt(user_query=state["query_str"], people_names=state.get("people_names", []))
                response = await self.llm.ainvoke(search_prompt)
                
                logger.info(f"LLM response for query extraction: {response.content}")
                
                try:
                    
                    json_data = self.image_searching_service.extract_json_from_llm_output(response.content, SearchResult)
                    if json_data:
                        search_result = {
                            "people": json_data.get("people", []),
                            "emotions": json_data.get("emotions", []),
                            "scene": json_data.get("scene", "")
                        }
                        errors = json_data.get("errors", [])
                        state["json_query_extraction"] = search_result
                        if len(errors) > 0:
                            raise ValueError(errors)
                        
                        logger.info(f"Extracted JSON data: {json_data}")
                    else:
                        raise ValueError("Failed to extract JSON data from LLM output")
                except Exception as e:
                    logger.error(f"Error extracting JSON from LLM output: {str(e)}")
                    self.add_error(state, f"Error extracting JSON from LLM output: {str(e)}")
                    
    
            return state
        
        except Exception as e:
            logger.error(f"Error in _get_data_from_search_query_node: {str(e)}")
            self.add_error(state, f"Error in _get_data_from_search_query_node: {str(e)}")
            return state
        
    async def _searching_based_on_people_node(self, state: ImageSearchingState) -> ImageSearchingState:
        
        try:

            # get the people name from json extraction
            logger.info(f"[_searching_based_on_people_node] Starting search based on people names.")
            people_names = state.get("json_query_extraction", {}).get("people", [])
            if not people_names:
                logger.info("[_searching_based_on_people_node] No people names found in the query extraction.")
                return state
            
            logger.info(f"[_searching_based_on_people_node] Searching based on people names: {people_names} ")
            
            face_detection_results = []
            for name in people_names:
                success, result = await self.image_searching_service.get_related_images_for_person(name)
                
                if success:
                    images = result.get("related_image_ids", [])
                    urls = result.get("image_links", [])
                    face_detection_results.append({
                        "person_name": name,
                        "related_image_ids": images,
                        "image_links": urls
                    })
                    logger.info(f"Found {len(images)} related images for person: {name}")
                else:
                    logger.warning(f"No related images found for person: {name}")
                    raise ValueError(result.get("error", "Unknown error"))
            
            state["face_detection_results"] = face_detection_results
            
            success, result = await self.image_searching_service.combine_face_detection_results(state["face_detection_results"])
            
            if success:
                state["face_detection_results_combined"] = result
                # logger.info(f"Combined face detection results: {result}")
            else:
                logger.warning("No combined face detection results found")
                raise ValueError(result.get("error", "Unknown error"))

            return state
        
        except Exception as e:
            logger.error(f"Error in _extract_images_data: {str(e)}")
            self.add_error(state, f"_searching_based_on_people_node: {str(e)}")
            return state
            
    async def _searching_based_on_scene_node(self, state: ImageSearchingState) -> ImageSearchingState:
        
        try:

            # get the scene description from json extraction
            scene_description = state.get("json_query_extraction", {}).get("scene", "")
            logger.info(f"[_searching_based_on_scene_node] Searching based on scene description: {scene_description} ")
            if not scene_description:
                logger.info("[_searching_based_on_scene_node] No scene description found in the query extraction.")
                return state
            
            success, result = await self.image_searching_service.get_images_based_on_scene(scene_description, state["project_id"])
            
            if success:
                state["scene_results"] = result
                logger.info(f"Found {len(result.get('related_image_ids', []))} related images for scene description.")
            else:
                logger.warning("No related images found for scene description.")
                raise ValueError(result.get("error", "Unknown error"))
            
            return state
        
        except Exception as e:
            logger.error(f"Error in _searching_based_on_scene_node: {str(e)}")
            self.add_error(state, f"_searching_based_on_scene_node: {str(e)}")
            return state
        
    async def _combine_searching_results_node(self, state: ImageSearchingState) -> ImageSearchingState:
        try:

            # Combine results from face-based and scene-based searching
            
            success, result = await self.image_searching_service.combine_search_results(
                face_results=state.get("face_detection_results_combined", {}),
                scene_results=state.get("scene_results", {})
            )
            if not success:
                raise ValueError(result.get("error", "Unknown error"))
            
            state["search_results"] = result
            logger.info(f"[_combine_searching_results_node] Found {len(result.get('related_image_ids', []))} related iamges for search query.")
            
            # logger.info(f"Combined searching results: {result}")
            
            return state
        
        except Exception as e:
            logger.error(f"Error in _combine_searching_results_node: {str(e)}")
            self.add_error(state, f"_combine_searching_results_node: {str(e)}")
            return state
        
    def add_error(self, state: ImageSearchingState, msg: str) -> None:
        if not state.get("errors"):
            state["errors"] = []
        state["errors"].append(msg)
        state["errors"] = list(dict.fromkeys(state["errors"]))
    
    def _build_graph(self) -> StateGraph:
        
        workflow = StateGraph(ImageSearchingState)
        
        workflow.add_node("get_people_names_from_supabase", self._get_people_names_from_supabase_node)
        workflow.add_node("get_data_from_search_query", self._get_data_from_search_query_node)
        workflow.add_node("searching_based_on_people", self._searching_based_on_people_node)
        workflow.add_node("searching_based_on_scene", self._searching_based_on_scene_node)
        workflow.add_node("combine_searching_results", self._combine_searching_results_node)
        
        # Define graph edges
        workflow.add_edge(START, "get_people_names_from_supabase")
        workflow.add_edge("get_people_names_from_supabase", "get_data_from_search_query")
        workflow.add_edge("get_data_from_search_query", "searching_based_on_people")
        workflow.add_edge("searching_based_on_people", "searching_based_on_scene")
        workflow.add_edge("searching_based_on_scene", "combine_searching_results")
        workflow.add_edge("combine_searching_results", END)
        
        return workflow.compile()
    
def create_image_searching_graph() -> ImageSearchingGraph:
    return ImageSearchingGraph()
        
            
    
    
