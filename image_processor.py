"""
Image processing utilities for MarkdownImageEmbedder.
"""

import io
import logging
import mimetypes
import os
from typing import Optional, Tuple

from PIL import Image


class ImageProcessor:
    """Handles image processing operations."""

    def __init__(self, quality_scale: int = 5):
        """
        Initialize the ImageProcessor.
        
        Args:
            quality_scale: Quality scale (1-9) that affects compression 
                           based on file size (1=highest quality, 9=lowest)
        """
        self.logger = logging.getLogger(__name__)
        self.quality_scale = quality_scale
        
        # Validate quality scale range
        if self.quality_scale < 1 or self.quality_scale > 9:
            self.logger.warning("Invalid quality scale value. Using default (5).")
            self.quality_scale = 5
            
        # Track the most recent compression results
        self.last_jpeg_quality: int = 0
        self.last_original_size: int = 0
        self.last_compressed_size: int = 0
        
        # Initialize MIME types
        mimetypes.init()

    def calculate_jpeg_quality(self, file_size_bytes: int) -> int:
        """
        Calculate the JPEG quality level based on file size and quality scale.
        
        Args:
            file_size_bytes: Size of the file in bytes
            
        Returns:
            int: The calculated JPEG quality (0-100)
        """
        # Define the file size thresholds in bytes
        SIZE_1KB = 1 * 1024
        SIZE_5KB = 5 * 1024
        SIZE_20KB = 20 * 1024
        SIZE_50KB = 50 * 1024
        SIZE_100KB = 100 * 1024
        SIZE_200KB = 200 * 1024
        
        # Quality table based on file size ranges and quality scale
        # Format: [file_size_range][quality_scale]
        quality_table = [
            # Quality Scale:   1    2    3    4    5    6    7    8    9
            [100, 100, 100, 100, 100, 100, 100, 100, 100],  # ~1KB
            [30, 45, 60, 75, 90, 92, 94, 96, 98],           # ~5KB
            [25, 37, 49, 60, 70, 77, 83, 89, 95],           # ~20KB
            [20, 28, 36, 43, 50, 60, 70, 80, 90],           # ~50KB
            [15, 22, 28, 34, 40, 52, 63, 74, 85],           # ~100KB
            [12, 16, 19, 22, 25, 40, 53, 67, 80],           # ~200KB
            [10, 12, 14, 16, 18, 33, 47, 61, 75]            # >=200KB
        ]
        
        # Determine row index based on file size
        if file_size_bytes <= SIZE_1KB:
            row_index = 0
        elif file_size_bytes <= SIZE_5KB:
            row_index = 1
        elif file_size_bytes <= SIZE_20KB:
            row_index = 2
        elif file_size_bytes <= SIZE_50KB:
            row_index = 3
        elif file_size_bytes <= SIZE_100KB:
            row_index = 4
        elif file_size_bytes <= SIZE_200KB:
            row_index = 5
        else:
            # For any file larger than 200KB, use the last row
            row_index = 6
            
        # Adjust the quality scale index (0-based)
        quality_scale_index = self.quality_scale - 1
        
        return quality_table[row_index][quality_scale_index]

    def compress_to_jpeg(self, input_data: bytes) -> Optional[bytes]:
        """
        Compress image data to JPEG format.
        
        Args:
            input_data: The original image data
            
        Returns:
            bytes: The compressed JPEG data, or None if compression failed or should be skipped
        """
        # Log original file size
        original_size = len(input_data)
        self.last_original_size = original_size
        
        # Calculate the JPEG quality based on file size and quality scale
        jpeg_quality = self.calculate_jpeg_quality(original_size)
        self.last_jpeg_quality = jpeg_quality
        
        # If quality is 100 and file is very small (≤ 1KB), return the original data
        if jpeg_quality == 100 and original_size <= 1024:
            self.logger.debug(f"Small image ({original_size} bytes): no compression needed")
            # Mark as no compression performed
            self.last_compressed_size = original_size
            return input_data
            
        try:
            # Open the image using PIL
            img = Image.open(io.BytesIO(input_data))
            
            # Create an output buffer
            output_buffer = io.BytesIO()
            
            # Check if image has alpha channel
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                # Convert transparent background to white
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])
                else:
                    background.paste(img, mask=img.convert('RGBA').split()[3])
                img = background
            
            # Save as JPEG with the calculated quality
            img.save(output_buffer, format='JPEG', quality=jpeg_quality, optimize=True)
            output_data = output_buffer.getvalue()
            
            # Store the compressed size
            self.last_compressed_size = len(output_data)
            
            return output_data
            
        except Exception as e:
            self.logger.error(f"Error compressing image: {e}")
            return None

    @staticmethod
    def get_mime_type(url: str) -> str:
        """
        Determine the MIME type from a URL.
        
        Args:
            url: The URL to analyze
            
        Returns:
            str: The MIME type
        """
        # Extract the file extension
        _, ext = os.path.splitext(url)
        if not ext:
            # Default to JPEG
            return "image/jpeg"
            
        # Normalize extension
        ext = ext.lower()
        
        # Common image types
        if ext == '.jpg' or ext == '.jpeg':
            return "image/jpeg"
        elif ext == '.png':
            return "image/png"
        elif ext == '.gif':
            return "image/gif"
        elif ext == '.bmp':
            return "image/bmp"
        elif ext == '.webp':
            return "image/webp"
        elif ext == '.svg':
            return "image/svg+xml"
        
        # Use mimetypes library as fallback
        mime_type, _ = mimetypes.guess_type(url)
        if mime_type and mime_type.startswith('image/'):
            return mime_type
            
        # Default to JPEG
        return "image/jpeg"

    def is_video_file(self, data: bytes) -> bool:
        """
        Check if the file data appears to be a video.
        
        Args:
            data: The file data to check
            
        Returns:
            bool: True if the file appears to be a video, False otherwise
        """
        if len(data) < 12:
            return False
            
        # Check for common video file signatures
        # MPEG Transport Stream
        if data[0:4] == b'\x00\x00\x01\xBA':
            return True
            
        # Matroska/WebM
        if data[0:4] == b'\x1A\x45\xDF\xA3':
            return True
            
        # MP4/QuickTime
        if data[4:8] == b'ftyp':
            return True
            
        # AVI
        if data[0:4] == b'RIFF' and data[8:12] == b'AVI ':
            return True
            
        # Flash Video
        if data[0:3] == b'FLV':
            return True
            
        return False
