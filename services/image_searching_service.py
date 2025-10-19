from core.config import get_settings
from services.base import BaseService
from langchain_core.output_parsers import JsonOutputParser
from fastapi import UploadFile
from deepface import DeepFace
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import cv2
import json
import traceback

class ImageSearchingService(BaseService):
    """ Service for searching images"""
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        
    def get_search_prompt(self, user_query: str, people_names: Optional[List[str]]) -> str:
        search_prompt = f"""
        
            You are a query parser for a multimodal search engine.

            Your task is to analyze a user's natural language search query and extract structured, relevant data that can be used for searching images or embeddings.

            User Query: "{user_query}"
            People Names: "{people_names if len(people_names) > 0 else 'None'}"
            
            ### Output Format (JSON only, no explanation, no prose):
            {{
              "people": [list of person names, if any],
              "emotions": [list of emotional states or facial expressions, if any],
              "objects": [list of physical objects mentioned, if any],
              "scenes": [list of environment or background descriptions, if any]
              "errors": [list of any errors encountered, if any]
            }}

            Guidelines:
            - If a category is not mentioned, return an empty list for it.
            - Do not invent data that isn't implied in the text.
            - Use lowercase words for non-proper nouns (e.g. "smiling", "car", "mountain").
            - Use lowercase for people names
            - Preserve exact names for people (e.g. "Alice", "Dr. John Smith").
            - Do not include explanations or commentary — return valid JSON only.
            - If people names are provided in the "User Query", ensure they are included in the "People Names" list, otherwise give error description in the "errors" list.
            - If there are some spelling mistakes in the "User Query" for the people names, and if they are recognizable from the "People Names" list (eg. User Query has name Alace and People Names list has a name Alice, so correct it), include them in the "people" list, otherwise give error description in the "errors" list.
            - Only include people names that are present in the "User Query" regardless of whether they are in the "People Names" list or not

            Example 1:
            User Query: "Find pictures of Alice and Bob smiling at a wedding."
            Output:
            {{
              "people": ["Alice", "Bob"],
              "emotions": ["smiling"],
              "objects": [],
              "scenes": ["wedding"]
            }}

            Example 2:
            User Query: "Search for angry people near cars on a rainy street."
            Output:
            {{
              "people": [],
              "emotions": ["angry"],
              "objects": ["car"],
              "scenes": ["rainy street"]
            }}

        
        """
        return search_prompt
    
    def extract_json_from_llm_output(self, llm_output: str, pydantic_object=None):
        """
        Extracts JSON from LLM output using LangChain's JsonOutputParser.
        Returns parsed JSON or raw string if parsing fails.
        Accepts an optional pydantic_object for schema validation.

        Args:
            llm_output: The output from the LLM
            pydantic_object: The pydantic object to parse the output into

        Returns:
            The parsed JSON or None if parsing fails

        Raises:
            Exception: If parsing fails
        """
        if pydantic_object is None:
            self.logger.error("No pydantic_object provided to extract_json_from_llm_output.")
            return None

        parser = JsonOutputParser(pydantic_object=pydantic_object)
        try:
            return parser.parse(llm_output)
        except Exception as e:
            self.logger.error(f"Error parsing LLM output: {e}")
            self.logger.error(f"Raw LLM output: {llm_output}")
            return None
        
    async def get_people_names_from_supabase(self, project_id: str) -> Tuple[bool, Dict[str, Any]]:
        
        try: 
            
            self.logger.info(f"Fetching people names in the available albums for project_id: {project_id}")
            response = self.db.table("albums").select("person_name").eq("project_id", project_id).execute()
            
            if not response.data:
                self.logger.info(f"No albums found for project_id: {project_id}")
                raise ValueError("Failed to fetch people names from albums")
            
            people_names = [item["person_name"] for item in response.data if item.get("person_name")]
            return True, {"people_names": people_names}
        
        except Exception as e:
            self.logger.error(f"Error fetching people names from Supabase: {e}")
            return False, {"error": str(e)}
            
    async def get_related_images_for_person(self, person_name: str) -> Tuple[bool, Dict[str, Any]]:
        
        try: 
            self.logger.info(f"Fetching related images for person: {person_name}")
            response = self.db.table("albums").select("image_group").eq("person_name", person_name).execute()
            
            if not response.data:
                raise ValueError(f"No albums found for person: {person_name}")
            
            # related_image_ids = []
            # for item in response.data:
            #     ids = item.get("related_image_ids", [])
            #     if isinstance(ids, list):
            #         related_image_ids.extend(ids)
            #     elif isinstance(ids, str):
            #         try:
            #             ids_list = json.loads(ids)
            #             if isinstance(ids_list, list):
            #                 related_image_ids.extend(ids_list)
            #         except json.JSONDecodeError:
            #             self.logger.warning(f"Failed to decode related_image_ids string for person {person_name}")
            album = response.data[0]
            related_image_ids = album.get("image_group", [])
            
            response = self.db.table("images") \
                .select("id, image_url") \
                .in_("id", related_image_ids) \
                .execute() 
                
            if not response.data:
                raise ValueError(f"No images found for related_image_ids of person: {person_name}")
            
            image_links = [item["image_url"] for item in response.data if item.get("image_url")]
            
            return True, {"related_image_ids": related_image_ids, "image_links": image_links}
        
        except Exception as e:
            self.logger.error(f"Error fetching related images for person {person_name}: {e}")
            return False, {"error": str(e)}        
        
    async def combine_face_detection_results(self, face_detection_results: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
        """
        Return image IDs that appear in all person results.
        """
        
        try: 

            if not face_detection_results:
                raise ValueError("No face detection results provided")

            if len(face_detection_results) == 1:
                return True, {
                    "related_image_ids": face_detection_results[0].get("related_image_ids", []),
                    "image_links": face_detection_results[0].get("image_links", [])
                }

            # Convert each list of related_image_ids into a set
            sets_related_image_ids = [set(person["related_image_ids"]) for person in face_detection_results if person.get("related_image_ids")]
            sets_image_links = [set(person["image_links"]) for person in face_detection_results if person.get("image_links")]

            if not sets_related_image_ids or not sets_image_links:
                raise ValueError("No valid related_image_ids or image_links found in face detection results")

            # Find intersection across all sets
            common_ids = set.intersection(*sets_related_image_ids)
            common_links = set.intersection(*sets_image_links)

            return True, {
                "related_image_ids": list(common_ids),
                "image_links": list(common_links)
            }
        except Exception as e:
            self.logger.error(f"Error combining face detection results: {str(e)}")
            return False, {"error": str(e)}
    