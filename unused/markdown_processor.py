"""
Markdown processing module for MarkdownImageEmbedder.
"""

import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

# Use direct imports instead of relative ones
from base64_encoder import Base64Encoder
from http_client import HttpClient
from image_processor import ImageProcessor


@dataclass
class ImageMatch:
    """Represents a matched image in markdown."""
    original_text: str  # Original markdown text
    alt_text: str  # Alt text for the image
    url: str  # URL or file path to the image
    position: int  # Position in the original markdown
    length: int  # Length of the match


class MarkdownProcessor:
    """Processes markdown and embeds images."""

    # Regular expression for markdown image links
    IMAGE_PATTERN = re.compile(r'!\[(?:[^\]]*?)(?:\|(?:[^\]]*?))?\]\((?!data:image)(?:[^\)]*?)\)')
    
    # Approximate size overhead for markdown embedded images
    MARKDOWN_IMAGE_OVERHEAD = 100  # Base64 data URL overhead in bytes

    def __init__(
        self, 
        http_client: HttpClient, 
        image_processor: ImageProcessor,
        yarle_mode: bool = False, 
        max_file_size_bytes: int = 5 * 1024 * 1024,
        base_path: str = ""
    ):
        """
        Initialize the MarkdownProcessor.
        
        Args:
            http_client: HTTP client for downloading images
            image_processor: Image processor for compressing images
            yarle_mode: Enable special handling for Yarle–generated files
            max_file_size_bytes: Maximum size allowed for embedded images
            base_path: Optional base path for resolving relative paths
        """
        self.logger = logging.getLogger('process')
        self.http_client = http_client
        self.image_processor = image_processor
        self.yarle_mode = yarle_mode
        self.max_file_size_bytes = max_file_size_bytes
        self.base_path = base_path
        
        # Statistics
        self.non_embedded_resources: Set[str] = set()
        self.total_image_size: int = 0
        self.total_compressed_size: int = 0
        self.total_output_size: int = 0
        self.images_processed: int = 0
        self.skipped_images: int = 0

    def process(self, markdown: str) -> str:
        """
        Process markdown and embed images.
        
        Args:
            markdown: The input markdown text
            
        Returns:
            str: The processed markdown with embedded images
        """
        original_markdown_size = len(markdown)
        
        # Reset statistics
        self.total_image_size = 0
        self.total_compressed_size = 0
        self.images_processed = 0
        self.skipped_images = 0
        self.non_embedded_resources.clear()
        
        # Find all image links in the markdown
        matches = self.find_image_links(markdown)
        self.logger.debug(f"Found {len(matches)} image links in markdown")
        
        # Process matches in forward order
        result = []
        last_pos = 0
        
        for match in matches:
            # Output the text between last match and this match
            if match.position > last_pos:
                result.append(markdown[last_pos:match.position])
                
            # Process the image match
            self.logger.debug(f"Processing image match at position {match.position}")
            embedded_image = self.process_image_match(match)
            result.append(embedded_image)
            
            # Update the last position
            last_pos = match.position + match.length
            
        # Output any remaining text after the last match
        if last_pos < len(markdown):
            result.append(markdown[last_pos:])
            
        # Join the result
        output = ''.join(result)
        self.total_output_size = len(output)
        
        # Log processing results
        self._log_processing_results(original_markdown_size)
        
        return output

    def _log_processing_results(self, original_markdown_size: int) -> None:
        """
        Log processing results.
        
        Args:
            original_markdown_size: Size of the original markdown in bytes
        """
        if self.images_processed == 0:
            self.logger.info("No images found.")
        else:
            compression_info = f"{self.images_processed} images converted: " + \
                               f"{self._format_file_size(self.total_image_size)} -> " + \
                               f"{self._format_file_size(self.total_compressed_size)}"
                               
            if self.total_image_size > 0:
                compression_ratio = self.total_compressed_size / self.total_image_size * 100.0
                compression_info += f" ({compression_ratio:.1f}%)"
                
            self.logger.info(compression_info)
            
        # Log size statistics
        total_original_size = original_markdown_size + self.total_image_size
        final_size = self.total_output_size
        
        size_info = f"Sizes: Original (md + {self.images_processed} images) = " + \
                    f"{self._format_file_size(total_original_size)} " + \
                    f"({self._format_file_size(original_markdown_size)} + " + \
                    f"{self._format_file_size(self.total_image_size)}), " + \
                    f"Final (md with {self.images_processed} images) = " + \
                    f"{self._format_file_size(final_size)}"
                    
        if total_original_size > 0:
            size_ratio = final_size / total_original_size * 100.0
            size_info += f" ({size_ratio:.0f}%)"
            
        self.logger.debug(size_info)

    def find_image_links(self, markdown: str) -> List[ImageMatch]:
        """
        Find all image links in the markdown.
        
        Args:
            markdown: The markdown text
            
        Returns:
            List[ImageMatch]: List of image matches
        """
        matches = []
        
        for match in self.IMAGE_PATTERN.finditer(markdown):
            match_text = match.group(0)
            position = match.start()
            length = len(match_text)
            
            # Skip empty image links
            if match_text == "![]()":
                continue
                
            # Process different image syntax formats
            if match_text.startswith("![[") and "]]" in match_text:
                # Obsidian/Yarle format: ![[path]]
                start = match_text.find("[[") + 2
                end = match_text.find("]]", start)
                if end != -1:
                    url = match_text[start:end]
                    alt_text = ""
                    matches.append(ImageMatch(match_text, alt_text, url, position, length))
            elif match_text.startswith("![") and "](" in match_text:
                # Standard markdown: ![alt](url)
                alt_start = match_text.find("[") + 1
                alt_end = match_text.find("]", alt_start)
                url_start = match_text.find("(", alt_end) + 1
                url_end = match_text.find(")", url_start)
                
                if alt_end != -1 and url_end != -1:
                    alt_text = match_text[alt_start:alt_end]
                    url = match_text[url_start:url_end]
                    
                    # Handle pipe character in alt text (for dimensions)
                    if "\\|" in alt_text:  # Escaped pipe
                        alt_text = alt_text.split("\\|")[0]
                    elif "|" in alt_text:  # Normal pipe
                        alt_text = alt_text.split("|")[0]
                        
                    matches.append(ImageMatch(match_text, alt_text, url, position, length))
                    
        return matches

    def resolve_file_path(self, path: str) -> str:
        """
        Attempt to resolve a local file path.
        
        Args:
            path: The path to resolve
            
        Returns:
            str: The resolved file path if found, empty string otherwise
        """
        # Clean up the path
        clean_path = path.rstrip('/\\"\' \t\r\n')
        
        # Try the path as-is
        if os.path.isfile(clean_path):
            return clean_path
            
        # If base path is provided, try joining with it
        if self.base_path:
            # Remove trailing slashes and quotes from base path
            base_path = self.base_path.rstrip('/\\"\' \t\r\n')
            
            # Handle relative paths
            relative_path = clean_path
            if relative_path.startswith("./"):
                relative_path = relative_path[2:]
                
            # Join paths
            full_path = os.path.join(base_path, relative_path)
            
            # Check if the full path exists
            if os.path.isfile(full_path):
                return full_path
                
        return ""

    def is_embedded_image(self, url: str) -> bool:
        """
        Check if a URL is already an embedded image.
        
        Args:
            url: The URL to check
            
        Returns:
            bool: True if the URL is an embedded image data URL
        """
        return url.startswith("data:image/") or url.startswith("data:image%2F")

    def process_image_match(self, match: ImageMatch) -> str:
        """
        Process a single image match and return the embedded markdown.
        
        Args:
            match: The image match to process
            
        Returns:
            str: The embedded image markdown or original text if embedding fails
        """
        url = match.url
        is_local_file = False
        image_data = None
        
        self.logger.debug(f"Processing image: {url}")
        
        # Handle Obsidian/Yarle syntax
        if url.startswith("[[") and url.endswith("]]"):
            url = url[2:-2]
            
        # Remove dimension specifications and clean up the URL
        if "|" in url:
            url = url.split("|")[0]
        if "\\|" in url:
            url = url.split("\\|")[0]
            
        # Clean up the URL by removing trailing spaces or special characters
        url = url.strip()
        
        # Skip already embedded images
        if self.is_embedded_image(url):
            self.logger.debug("Preserving already embedded image")
            return match.original_text
            
        # Handle Yarle resource paths
        if self.yarle_mode and not url.startswith(("http://", "https://")):
            if "./_resources/" in url or ".resources/" in url:
                self.logger.debug(f"Handling Yarle resource path: {url}")
                resolved_path = self.resolve_file_path(url)
                if resolved_path:
                    url = resolved_path
                    self.logger.debug(f"Resolved to: {url}")
                    
        # Handle local files vs remote URLs
        if not url.startswith(("http://", "https://")):
            is_local_file = True
            
            # Try to resolve the path if it doesn't exist as-is
            if not os.path.isfile(url):
                resolved_path = self.resolve_file_path(url)
                if resolved_path:
                    url = resolved_path
                else:
                    self.logger.debug(f"Failed to resolve local file: {url}")
                    self.non_embedded_resources.add(url)
                    return match.original_text
                    
            # Read the file
            try:
                with open(url, "rb") as f:
                    image_data = f.read()
            except Exception as e:
                self.logger.error(f"Error reading local file: {url} - {e}")
                self.non_embedded_resources.add(url)
                return match.original_text
        else:
            # Download from URL
            image_data = self.http_client.download_data(url)
            if not image_data:
                self.logger.debug(f"Failed to download image: {url}")
                self.non_embedded_resources.add(url)
                return match.original_text
                
        # Check if it's a video file
        if self.image_processor.is_video_file(image_data):
            self.logger.debug(f"Skipping video file: {url}")
            self.non_embedded_resources.add(url)
            return match.original_text
            
        # Get the MIME type
        mime_type = ImageProcessor.get_mime_type(url)
        if not mime_type:
            self.logger.debug(f"Unsupported file type: {url}")
            self.non_embedded_resources.add(url)
            return match.original_text
            
        # Update the total image size
        self.total_image_size += len(image_data)
        
        # Compress the image
        try:
            compressed_data = self.image_processor.compress_to_jpeg(image_data)
            if not compressed_data:
                self.logger.debug(f"Image compression failed: {url}")
                self.non_embedded_resources.add(url)
                return match.original_text
                
            # Update the compressed size
            self.total_compressed_size += len(compressed_data)
            self.images_processed += 1
            
            # Log compression results
            self.logger.debug(
                f"Embedding [{url}](JPEG quality {self.image_processor.last_jpeg_quality}%): "
                f"{self._format_file_size(self.image_processor.last_original_size)} -> "
                f"{self._format_file_size(self.image_processor.last_compressed_size)}"
            )
            
            # Encode as base64
            base64_data = Base64Encoder.encode(compressed_data)
            
            # Calculate approximate final size
            final_size = len(base64_data) + self.MARKDOWN_IMAGE_OVERHEAD
            
            # Check if the final size exceeds the maximum allowed size
            if final_size > self.max_file_size_bytes:
                self.logger.debug(
                    f"Base64 encoded image too large: {url} "
                    f"({self._format_file_size(final_size)}) > "
                    f"{self._format_file_size(self.max_file_size_bytes)}"
                )
                self.non_embedded_resources.add(url)
                return match.original_text
                
            # Preserve the original alt text and dimensions
            alt_text = match.alt_text
            dimensions = ""
            
            # Check for dimensions in alt text
            pipe_pos = alt_text.find("|")
            if pipe_pos != -1:
                dimensions = alt_text[pipe_pos:]
                alt_text = alt_text[:pipe_pos]
                
            # Create the embedded image markdown
            embedded_image = f"![{alt_text}{dimensions}](data:{mime_type};base64,{base64_data})"
            
            # Handle clickable images
            make_clickable = False
            link_target = ""
            
            if not is_local_file and url.startswith(("http://", "https://")):
                make_clickable = True
                link_target = url
            elif match.alt_text.startswith(("http://", "https://")):
                make_clickable = True
                link_target = match.alt_text
                
            if make_clickable:
                # Clean up the link target
                if "|" in link_target:
                    link_target = link_target.split("|")[0]
                if "\\|" in link_target:
                    link_target = link_target.split("\\|")[0]
                    
                # Create a clickable image
                return f"[![{alt_text}{dimensions}](data:{mime_type};base64,{base64_data})]({link_target})"
            else:
                return embedded_image
                
        except Exception as e:
            self.logger.error(f"Error processing image: {url} - {e}")
            self.non_embedded_resources.add(url)
            return match.original_text
            
    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """
        Format a file size in human-readable form.
        
        Args:
            size_bytes: The size in bytes
            
        Returns:
            str: The formatted file size
        """
        # Define units
        units = ["B", "KB", "MB", "GB", "TB"]
        
        # Handle zero size
        if size_bytes == 0:
            return "0 B"
            
        # Calculate appropriate unit
        unit_index = 0
        while size_bytes >= 1024 and unit_index < len(units) - 1:
            size_bytes /= 1024.0
            unit_index += 1
            
        # Format with one decimal place
        return f"{size_bytes:.1f} {units[unit_index]}"
