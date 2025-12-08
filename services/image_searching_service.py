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
from transformers import CLIPProcessor, CLIPModel
import torch
import faiss

class ImageSearchingService(BaseService):
    """ Service for searching images"""
    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self._load_clip()
    
    def _load_clip(self):
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32", use_fast=True)
        self.clip_model.eval()

        
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
              "scenes": ""
              "errors": [list of any errors encountered, if any]
            }}

            Guidelines:
            - If a category is not mentioned, return an empty list for "people" or "emotions" and an empty string for "scene".
            - Do not invent data that isn't implied in the text.
            - Use lowercase words for non-proper and even proper nouns.
            - Use lowercase for people names
            - Preserve exact names for people (e.g. "Alice", "Dr. John Smith").
            - Do not include explanations or commentary — return valid JSON only.
            - If people names are provided in the "User Query", ensure they are included in the "People Names" list, otherwise give error description in the "errors" list.
            - If there are some spelling mistakes in the "User Query" for the people names, and if they are recognizable from the "People Names" list (eg. User Query has name Alace and People Names list has a name Alice, so correct it), include them in the "people" list, otherwise give error description in the "errors" list.
            - Only include people names that are present in the "User Query" regardless of whether they are in the "People Names" list or not
            - Extract scene as a single descriptive string that summarizes the physical setting, background elements, environment, or context, excluding people (e.g., "iamges with mountains in the background", "images with person wearing formals", "pictures with rainy street with cars", "pictures with beach at sunset").
            - Ensure the scene description is literal, and general and do not interpret or summarize beyond what is in the text.

            Example 1:
            User Query: "Find pictures of Alice and Bob smiling at a wedding."
            Output:
            {{
              "people": ["Alice", "Bob"],
              "emotions": ["smiling"],
              "scene": "pictures of people smiling at a wedding",
            }}

            Example 2:
            User Query: "images with angry people near cars on a rainy street."
            Output:
            {{
              "people": [],
              "emotions": ["angry"],
              "scene": "images with people near cars on a rainy street"
            }}
            
            Example 3:
            User Query: "images of hamza with eagles"
            Output:
            {{
              "people": ["hamza"],
              "emotions": [""],
              "scene": "images with eagles"
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
    
    async def get_images_based_on_scene(self, scene_description: str, project_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Fetch images related to the scene description using Supabase.
        """
        
        try:
            self.logger.info(f"Fetching images related to scene description: {scene_description}")

            response = self.db.table("images").select("id, image_url, image_embeddings").eq("project_id", project_id).execute()
            data = response.data

            if not data:
                raise ValueError(f"No images found for project_id: {project_id}")

            valid_items = [item for item in data if item.get("image_embeddings")]
            if not valid_items:
                raise ValueError(f"No images with embeddings found for project_id: {project_id}")

            image_embeddings = []
            image_metadata = []

            for item in valid_items:
                embedding = item["image_embeddings"]
                if isinstance(embedding, str):
                    embedding = embedding.strip("[]")
                    embedding = np.array([float(x.strip()) for x in embedding.split(',')], dtype=np.float32)
                elif isinstance(embedding, list):
                    embedding = np.array(embedding, dtype=np.float32)
                else:
                    self.logger.warning(f"Skipping image {item['id']} - unexpected embedding format")
                    continue

                image_embeddings.append(embedding)
                image_metadata.append({"id": item["id"], "image_url": item["image_url"]})

            if not image_embeddings:
                raise ValueError(f"No valid embeddings found for project_id: {project_id}")

            embeddings_matrix = np.vstack(image_embeddings).astype('float32')
            faiss.normalize_L2(embeddings_matrix)

            dimension = embeddings_matrix.shape[1]
            index = faiss.IndexFlatIP(dimension)
            index.add(embeddings_matrix)

            scene_embedding = await self._get_text_embedding(scene_description)
            scene_embedding = np.array(scene_embedding, dtype=np.float32).reshape(1, -1)
            faiss.normalize_L2(scene_embedding)

            distances, indices = index.search(scene_embedding, len(image_metadata))

            similarity_threshold = 0.25
            related_images = []
            for distance, idx in zip(distances[0], indices[0]):
                if distance >= similarity_threshold:
                    related_images.append({
                        "id": image_metadata[idx]["id"],
                        "image_url": image_metadata[idx]["image_url"],
                        "similarity_score": float(distance)
                    })

            related_images.sort(key=lambda x: x["similarity_score"], reverse=True)

            return True, {
                "related_image_ids": [img["id"] for img in related_images],
                "image_links": [img["image_url"] for img in related_images],
                # "similarity_scores": [img["similarity_score"] for img in related_images],
                # "count": len(related_images)
            }

        except Exception as e:
            self.logger.error(f"Error fetching images based on scene description: {e}")
            return False, {"error": str(e)}
    
    async def _get_text_embedding(self, text: str) -> List[float]:
        inputs = self.clip_processor(text=[text], return_tensors="pt", padding=True)
        with torch.no_grad():
            text_features = self.clip_model.get_text_features(**inputs)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        return text_features.cpu().numpy().flatten().tolist()
    
    async def combine_search_results(self, face_results: Dict[str, Any], scene_results: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Return only image IDs and links that appear in BOTH face results and scene results.
        """
        try:
            if not face_results and not scene_results:
                raise ValueError("No search results provided")
    
            if not face_results:
                return True, scene_results
    
            if not scene_results:
                return True, face_results
    
            # Build sets of IDs
            face_ids = set(face_results.get("related_image_ids", []))
            scene_ids = set(scene_results.get("related_image_ids", []))
    
            # Intersection
            common_ids = face_ids.intersection(scene_ids)
    
            # Build proper maps (image_id → image_url)
            face_map = dict(zip(
                face_results.get("related_image_ids", []),
                face_results.get("image_links", [])
            ))
    
            scene_map = dict(zip(
                scene_results.get("related_image_ids", []),
                scene_results.get("image_links", [])
            ))
    
            combined_links_set = set()

            for img_id in common_ids:
                if img_id in face_map:
                    combined_links_set.add(face_map[img_id])
                elif img_id in scene_map:
                    combined_links_set.add(scene_map[img_id])

            combined_links = list(combined_links_set)
    
            return True, {
                "related_image_ids": list(common_ids),
                "image_links": combined_links
            }
    
        except Exception as e:
            self.logger.error(f"Error combining search results: {str(e)}")
            return False, {"error": str(e)}