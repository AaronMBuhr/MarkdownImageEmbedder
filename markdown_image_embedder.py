#!/usr/bin/env python3
"""
Markdown Image Embedder - A utility to embed images in markdown files as base64 encoded data URLs.

This is a standalone script version that doesn't rely on package imports.
"""

import argparse
import base64
import io
import logging
import mimetypes
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Set

import requests
from PIL import Image

# Set up logging
logging.basicConfig(format='%(levelname)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger('markdown-image-embedder')
logger.setLevel(logging.INFO)

# Constants
MARKDOWN_IMAGE_OVERHEAD = 100  # Base64 data URL overhead in bytes


@dataclass
class CommandLineOptions:
    """Holds the parsed command line options."""
    debug: bool = False
    verbose: bool = False
    yarle_mode: bool = False
    input_file: Optional[str] = None
    output_file: Optional[str] = None
    base_path: str = ""
    quality_scale: int = 5  # Default 5 (1-9 scale, lower = higher quality)
    max_file_size_mb: int = 10  # Maximum size for embedded files in MB


@dataclass
class ImageMatch:
    """Represents a matched image in markdown."""
    original_text: str  # Original markdown text
    alt_text: str  # Alt text for the image
    url: str  # URL or file path to the image
    position: int  # Position in the original markdown
    length: int  # Length of the match


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Embed images in markdown files as base64 encoded data URLs."
    )

    parser.add_argument(
        "--input-file", "-i", type=str,
        help="Use FILE as input instead of stdin"
    )
    parser.add_argument(
        "--output-file", "-o", type=str,
        help="Write output to FILE instead of stdout"
    )
    parser.add_argument(
        "--quality", "-q", type=int, default=5, choices=range(1, 10),
        help="Set quality scale from 1-9 (default: 5). Lower values = higher quality but larger files"
    )
    parser.add_argument(
        "--yarle", "-y", action="store_true",
        help="Enable Yarle compatibility mode"
    )
    parser.add_argument(
        "--max-size", "-m", type=int, default=10,
        help="Maximum file size to embed in MB (default: 10)"
    )
    parser.add_argument(
        "--path", "-p", type=str, default="",
        help="Base path for resolving relative file paths"
    )
    parser.add_argument(
        "--debug", "-d", action="store_true",
        help="Enable debug logging level"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging level"
    )

    args = parser.parse_args()
    
    # If path is not specified but input file is, use the input file's directory as base path
    base_path = args.path
    if not base_path and args.input_file:
        base_path = os.path.dirname(os.path.abspath(args.input_file))
        logger.debug(f"Using input file directory as base path: {base_path}")
    
    options = CommandLineOptions(
        debug=args.debug,
        verbose=args.verbose,
        yarle_mode=args.yarle,
        input_file=args.input_file,
        output_file=args.output_file,
        base_path=base_path,
        quality_scale=args.quality,
        max_file_size_mb=args.max_size
    )
    
    return options


def format_file_size(size_bytes: int) -> str:
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


def is_video_file(data: bytes) -> bool:
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


def calculate_jpeg_quality(file_size_bytes: int, quality_scale: int) -> int:
    """
    Calculate the JPEG quality level based on file size and quality scale.
    
    Args:
        file_size_bytes: Size of the file in bytes
        quality_scale: Quality scale (1-9, lower = higher quality)
        
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
    quality_scale_index = quality_scale - 1
    
    return quality_table[row_index][quality_scale_index]


def compress_to_jpeg(input_data: bytes, quality_scale: int, url: str = "") -> tuple[Optional[bytes], int, int, int]:
    """
    Compress image data to JPEG format.
    
    Args:
        input_data: The original image data
        quality_scale: Quality scale (1-9, lower = higher quality)
        url: The URL or file path of the image (for error reporting)
        
    Returns:
        tuple: (compressed_data, jpeg_quality, original_size, compressed_size)
    """
    # Log original file size
    original_size = len(input_data)
    
    # Calculate the JPEG quality based on file size and quality scale
    jpeg_quality = calculate_jpeg_quality(original_size, quality_scale)
    
    # If quality is 100 and file is very small (≤ 1KB), return the original data
    if jpeg_quality == 100 and original_size <= 1024:
        logger.debug(f"Small image ({original_size} bytes): no compression needed")
        return input_data, jpeg_quality, original_size, original_size
        
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
        compressed_size = len(output_data)
        
        return output_data, jpeg_quality, original_size, compressed_size
        
    except Exception as e:
        error_msg = f"Error compressing image: {e}"
        if url:
            error_msg += f" for URL: {url}"
        logger.error(error_msg)
        return None, 0, original_size, 0


def download_image(url: str) -> Optional[bytes]:
    """
    Download image data from a URL.
    
    Args:
        url: The URL to download from
        
    Returns:
        bytes: The downloaded data, or None if download failed
    """
    try:
        logger.debug(f"Downloading from URL: {url}")
        response = requests.get(url, timeout=30)
        
        if response.status_code != 200:
            logger.warning(f"Failed to download: {url} - Status code: {response.status_code}")
            return None
            
        logger.debug(f"Download successful: {url} - Size: {len(response.content)} bytes")
        return response.content
        
    except requests.RequestException as e:
        logger.error(f"Error downloading {url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading {url}: {str(e)}")
        return None


def find_image_links(markdown: str) -> List[ImageMatch]:
    """
    Find all image links in the markdown.
    
    This function now supports both:
      - Standard markdown images: ![alt text](url)
      - Obsidian-style images: ![[url]] (with optional dimension info via a pipe)
    
    Args:
        markdown: The markdown text.
        
    Returns:
        List[ImageMatch]: List of image matches.
    """
    # This pattern matches:
    # 1. Obsidian-style links: ![[...]]
    # 2. Standard markdown links: ![alt text](url)
    IMAGE_PATTERN = re.compile(
        r'(?P<obsidian>!\[\[(?P<obsidian_url>.*?)\]\])|'
        r'(?P<standard>!\[(?P<alt>[^\]]*?)(?:\|(?:[^\]]*?))?\]\((?!data:image)(?P<url>[^\)]*?)\))'
    )
    
    matches = []
    
    for match in IMAGE_PATTERN.finditer(markdown):
        position = match.start()
        if match.group("obsidian"):
            # Obsidian/Yarle syntax, e.g.:
            # ![[./_resources/.../unknown_filename.7.jpeg\|825x464]]
            match_text = match.group("obsidian")
            url = match.group("obsidian_url")
            alt_text = ""
        elif match.group("standard"):
            # Standard markdown image, e.g.:
            # ![alt text](url)
            match_text = match.group("standard")
            alt_text = match.group("alt") or ""
            url = match.group("url")
        else:
            continue
        
        # Append a new ImageMatch instance.
        matches.append(ImageMatch(match_text, alt_text, url, position, len(match_text)))
        
    return matches


def resolve_file_path(path: str, base_path: str) -> str:
    """
    Attempt to resolve a local file path.
    
    Args:
        path: The path to resolve
        base_path: Base path for resolving relative paths
        
    Returns:
        str: The resolved file path if found, empty string otherwise
    """
    # Clean up the path
    clean_path = path.rstrip('/\\"\' \t\r\n')
    
    # Try the path as-is
    if os.path.isfile(clean_path):
        return clean_path
        
    # If base path is provided, try joining with it
    if base_path:
        # Remove trailing slashes and quotes from base path
        base_path = base_path.rstrip('/\\"\' \t\r\n')
        
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


def is_embedded_image(url: str) -> bool:
    """
    Check if a URL is already an embedded image.
    
    Args:
        url: The URL to check
        
    Returns:
        bool: True if the URL is an embedded image data URL
    """
    return url.startswith("data:image/") or url.startswith("data:image%2F")


def split_on_unescaped_pipe(text: str) -> tuple[str, str | None]:
    """
    Splits the given text at the first unescaped pipe.
    
    Returns:
        A tuple (before, after) where:
          - 'before' is the text before the first unescaped pipe,
          - 'after' is the pipe and everything after it, or None if no unescaped pipe is found.
    
    For example:
      split_on_unescaped_pipe(r"example\|literal|dimensions") -> (r"example\|literal", "|dimensions")
      split_on_unescaped_pipe("no pipe here") -> ("no pipe here", None)
    """
    match = re.search(r'(?<!\\)\|', text)
    if match:
        pos = match.start()
        return text[:pos], text[pos:]
    else:
        return text, None


def process_image_match(match: ImageMatch, options: CommandLineOptions, stats: dict) -> str:
    """
    Process a single image match and return the embedded markdown.
    
    This revised version uses split_on_unescaped_pipe() so that escaped pipes
    (i.e. "\|") are treated as literal and not as delimiters for dimensions.
    
    Args:
        match: The image match to process.
        options: Command line options.
        stats: Dictionary for tracking statistics.
        
    Returns:
        The embedded image markdown or the original text if embedding fails.
    """
    url = match.url
    is_local_file = False
    image_data = None

    logger.debug(f"Processing image: {url}")

    # Clean up the URL by removing any dimension specifications,
    # but only split on unescaped pipes.
    url, _ = split_on_unescaped_pipe(url)
    url = url.strip()

    # If the URL is already embedded, preserve it.
    if is_embedded_image(url):
        logger.info("Preserving already embedded image.")
        return match.original_text

    # Handle Yarle resource paths.
    if options.yarle_mode and not url.startswith(("http://", "https://")):
        if "./_resources/" in url or ".resources/" in url:
            logger.debug(f"Handling Yarle resource path: {url}")
            resolved_path = resolve_file_path(url, options.base_path)
            if resolved_path:
                url = resolved_path
                logger.debug(f"Resolved to: {url}")

    # Process local files vs remote URLs.
    if not url.startswith(("http://", "https://")):
        is_local_file = True
        if not os.path.isfile(url):
            resolved_path = resolve_file_path(url, options.base_path)
            if resolved_path:
                url = resolved_path
            else:
                logger.debug(f"Failed to resolve local file: {url}")
                stats["non_embedded_resources"].add(url)
                return match.original_text
        try:
            with open(url, "rb") as f:
                image_data = f.read()
        except Exception as e:
            logger.error(f"Error reading local file: {url} - {e}")
            stats["non_embedded_resources"].add(url)
            return match.original_text
    else:
        image_data = download_image(url)
        if not image_data:
            logger.debug(f"Failed to download image: {url}")
            stats["non_embedded_resources"].add(url)
            return match.original_text

    # Skip processing if the data appears to be a video.
    if is_video_file(image_data):
        logger.info(f"Skipping video file: {url}")
        stats["non_embedded_resources"].add(url)
        return match.original_text

    mime_type = get_mime_type(url)
    if not mime_type:
        logger.debug(f"Unsupported file type: {url}")
        stats["non_embedded_resources"].add(url)
        return match.original_text

    # Compress the image.
    compressed_data, jpeg_quality, original_size, compressed_size = compress_to_jpeg(image_data, options.quality_scale, url)
    if not compressed_data:
        logger.debug(f"Image compression failed: {url}")
        stats["non_embedded_resources"].add(url)
        return match.original_text

    stats["total_image_size"] += original_size
    stats["total_compressed_size"] += compressed_size

    logger.info(
        f"Embedding [{url}](JPEG quality {jpeg_quality}%): {format_file_size(original_size)} -> {format_file_size(compressed_size)}"
    )

    # Encode the (compressed) image as base64.
    base64_data = base64.b64encode(compressed_data).decode('ascii')
    final_size = len(base64_data) + MARKDOWN_IMAGE_OVERHEAD
    max_file_size_bytes = options.max_file_size_mb * 1024 * 1024
    if final_size > max_file_size_bytes:
        logger.debug(
            f"Base64 encoded image too large: {url} ({format_file_size(final_size)}) > {format_file_size(max_file_size_bytes)}"
        )
        stats["non_embedded_resources"].add(url)
        return match.original_text

    # Process the alt text and any dimension info.
    alt_text = match.alt_text
    alt_text, dimensions = split_on_unescaped_pipe(alt_text)
    # # Remove escape backslashes so that "\|" becomes a literal pipe.
    # alt_text = alt_text.replace(r'\|', '|')
    alt_text = alt_text.replace('\\', '')
    
    if dimensions:
        dimensions = dimensions.replace(r'\|', '|')
    else:
        dimensions = ""

    embedded_image = f"![{alt_text}{dimensions}](data:{mime_type};base64,{base64_data})"

    # If the image should be clickable, use the original (cleaned) URL as the link target.
    make_clickable = False
    link_target = ""
    if not is_local_file and url.startswith(("http://", "https://")):
        make_clickable = True
        link_target = url.replace('\\', '')
    elif match.alt_text.startswith(("http://", "https://")):
        make_clickable = True
        link_target = match.alt_text.replace('\\', '')

    if make_clickable:
        # Also clean the link target for unescaped pipes.
        link_target, _ = split_on_unescaped_pipe(link_target)
        link_target = link_target.replace('\\', '')
        return f"[![{alt_text}{dimensions}](data:{mime_type};base64,{base64_data})]({link_target})"
    else:
        return embedded_image


def process_markdown(markdown: str, options: CommandLineOptions) -> tuple[str, dict]:
    """
    Process markdown text and embed images.
    
    Args:
        markdown: The input markdown text.
        options: Command line options.
        
    Returns:
        tuple: (processed_markdown, statistics)
    """
    original_markdown_size = len(markdown)

    # Initialize statistics.
    stats = {
        "total_image_size": 0,       # Sum of original image sizes (in bytes)
        "total_compressed_size": 0,    # Sum of compressed image sizes (in bytes)
        "total_output_size": 0,        # Size of the final markdown output
        "images_processed": 0,         # Count of images that were embedded
        "skipped_images": 0,           # Count of images that were not embedded
        "non_embedded_resources": set()
    }

    matches = find_image_links(markdown)
    logger.info(f"Found {len(matches)} image links in markdown")

    result = []
    last_pos = 0
    for match in matches:
        # Append text between matches.
        if match.position > last_pos:
            result.append(markdown[last_pos:match.position])
        logger.debug(f"Processing image match at position {match.position}")
        embedded_image = process_image_match(match, options, stats)
        result.append(embedded_image)
        last_pos = match.position + match.length

        # Update processing counts.
        if embedded_image != match.original_text:
            stats["images_processed"] += 1
        else:
            stats["skipped_images"] += 1

    # Append any remaining text.
    if last_pos < len(markdown):
        result.append(markdown[last_pos:])

    output = ''.join(result)
    stats["total_output_size"] = len(output)

    total_original_size = original_markdown_size + stats["total_image_size"]
    final_size = stats["total_output_size"]
    compression_ratio = (final_size / total_original_size * 100) if total_original_size > 0 else 0

    logger.info(
        f"Sizes: Original (md + {stats['images_processed']} images) = {format_file_size(total_original_size)} "
        f"({format_file_size(original_markdown_size)} + {format_file_size(stats['total_image_size'])}), "
        f"Final (md with {stats['images_processed']} images) = {format_file_size(final_size)} "
        f"({compression_ratio:.0f}%)"
    )

    return output, stats


def main():
    """Main entry point for the application."""
    # Parse command line options
    options = parse_arguments()
    
    # Set log level
    if options.debug:
        logger.setLevel(logging.DEBUG)
    elif options.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)
    
    try:
        # Read input
        logger.info("Reading input...")
        input_markdown = ""
        
        if options.input_file:
            try:
                with open(options.input_file, 'r', encoding='utf-8') as f:
                    input_markdown = f.read()
                logger.info(f"Read input from file: {options.input_file}")
            except Exception as e:
                logger.error(f"Error reading input file: {e}")
                return 1
        else:
            # Read from stdin
            try:
                input_markdown = sys.stdin.read()
                logger.info("Read input from stdin")
            except Exception as e:
                logger.error(f"Error reading from stdin: {e}")
                return 1
            
        # Process markdown
        logger.info("Processing markdown...")
        output_markdown, stats = process_markdown(input_markdown, options)
        
        # Write output
        try:
            if options.output_file:
                with open(options.output_file, 'w', encoding='utf-8') as f:
                    f.write(output_markdown)
                logger.info(f"Wrote output to file: {options.output_file}")
            else:
                # Write to stdout
                sys.stdout.write(output_markdown)
                sys.stdout.flush()
                logger.info("Wrote output to stdout")
        except Exception as e:
            logger.error(f"Error writing output: {e}")
            return 1
            
        # Log statistics
        if stats["images_processed"] > 0:
            logger.info(f"{stats['images_processed']} images processed")
            
        # Log non-embedded resources
        if stats["non_embedded_resources"]:
            logger.info("\nThe following resources were not embedded and need to be preserved:")
            for resource in stats["non_embedded_resources"]:
                logger.info(f"  {resource}")
                
        return 0
        
    except Exception as e:
        logger.error(f"Error: {e}")
        if options.debug:
            logger.exception("Stack trace:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
