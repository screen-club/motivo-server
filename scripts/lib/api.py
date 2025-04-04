# lib/api.py

import requests
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, base_url: str = "http://localhost:5002"):
        self.base_url = base_url.rstrip('/')
        
    def add_config(self, 
                   title: str, 
                   data: Dict[str, Any], 
                   type: str = "pose",
                   thumbnail: str = "",
                   cache_file_path: str = None,
                   users: List[str] = None,
                   ) -> Dict[str, Any]:
        """
        Add a new configuration to the database
        
        Args:
            title: Name of the animation/configuration
            data: Animation/pose data
            type: Type of configuration (default: "pose")
            thumbnail: Optional thumbnail URL
            cache_file_path: Optional path to cached file
            
        Returns:
            Created configuration object
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/conf",
                json={
                    "title": title,
                    "type": type,
                    "data": data,
                    "thumbnail": thumbnail,
                    "cache_file_path": cache_file_path,
                    "users": users,
                }
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error adding config: {e}")
            raise