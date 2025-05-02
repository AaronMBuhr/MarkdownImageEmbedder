"""
HTTP client for downloading images from URLs.
"""

from abc import ABC, abstractmethod
import logging
from typing import Optional

import requests
from requests.exceptions import RequestException


class HttpClient(ABC):
    """Abstract base class for HTTP operations."""

    @abstractmethod
    def download_data(self, url: str) -> Optional[bytes]:
        """
        Download data from a URL.
        
        Args:
            url: The URL to download from
            
        Returns:
            bytes: The downloaded data, or None if download failed
        """
        pass


class RequestsClient(HttpClient):
    """Implementation of HttpClient using the requests library."""

    def download_data(self, url: str) -> Optional[bytes]:
        """
        Download data from a URL using the requests library.
        
        Args:
            url: The URL to download from
            
        Returns:
            bytes: The downloaded data, or None if download failed
        """
        logger = logging.getLogger(__name__)
        
        try:
            logger.debug(f"Downloading from URL: {url}")
            response = requests.get(url, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"Failed to download: {url} - Status code: {response.status_code}")
                return None
                
            logger.debug(f"Download successful: {url} - Size: {len(response.content)} bytes")
            return response.content
            
        except RequestException as e:
            logger.error(f"Error downloading {url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading {url}: {str(e)}")
            return None


def create_http_client() -> HttpClient:
    """
    Factory function to create an HTTP client.
    
    Returns:
        HttpClient: An instance of an HttpClient implementation
    """
    return RequestsClient()
