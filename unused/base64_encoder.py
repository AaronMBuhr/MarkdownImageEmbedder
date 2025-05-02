"""
Base64 encoding utilities for MarkdownImageEmbedder.
"""

import base64
from typing import Union


class Base64Encoder:
    """Utility class for encoding binary data as base64."""

    @staticmethod
    def encode(data: Union[bytes, bytearray]) -> str:
        """
        Encode binary data to a base64 string.
        
        Args:
            data: The binary data to encode
            
        Returns:
            str: The base64 encoded string
        """
        return base64.b64encode(data).decode('ascii')
