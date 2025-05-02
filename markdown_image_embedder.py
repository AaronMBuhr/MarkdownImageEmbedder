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
from typing import List, Optional, Set, Tuple

import requests
from PIL import Image

# Set up logging early so we can log any import issues.
logging.basicConfig(format='%(levelname)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger('markdown-image-embedder')
logger.setLevel(logging.INFO)

# Try to import SVG support libraries.
try:
    from svglib.svglib import svg2rlg
    from reportlab.graphics import renderPM
    SVG_SUPPORT = True
except ImportError:
    SVG_SUPPORT = False
    logger.warning("svglib and reportlab packages not installed. SVG files will be skipped. Install with: pip install svglib reportlab")

# Constants
MARKDOWN_IMAGE_OVERHEAD = 100  # Base64 data URL overhead in bytes

@dataclass
class CommandLineOptions:
    """Holds the parsed command line options."""
    debug: bool = False
    verbose: bool = False
    quiet: bool = False
    yarle_mode: bool = False
    input_file: Optional[str] = None
    output_file: Optional[str] = None
    log_file: Optional[str] = None
    base_path: str = ""
    quality_scale: int = 5  # Default 5 (1-9 scale, lower = higher quality)
    max_file_size_mb: int = 10  # Maximum size for embedded files in MB
    max_width: Optional[int] = None  # Maximum width for images in pixels
    max_height: Optional[int] = None  # Maximum height for images in pixels

@dataclass
class ImageMatch:
    """Represents a matched image in markdown."""
    original_text: str  # Original markdown text
    alt_text: str       # Alt text for the image
    url: str            # URL or file path to the image
    position: int       # Position in the original markdown
    length: int         # Length of the match

class LogFilter(logging.Filter):
    """Filter to control which log records are emitted."""
    def __init__(self, quiet=False):
        super().__init__()
        self.quiet = quiet
        
    def filter(self, record):
        # In quiet mode, only let through ERROR or higher level messages
        if self.quiet and record.levelno < logging.ERROR:
            return False
        return True

def configure_logging(options: CommandLineOptions):
    """Configure logging based on command line options."""
    # Set logging level based on options
    if options.debug:
        logger.setLevel(logging.DEBUG)
    elif options.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)
    
    # Apply quiet filter if requested
    if options.quiet:
        for handler in logger.handlers:
            handler.addFilter(LogFilter(quiet=True))
    
    # Add file handler if log file specified
    if options.log_file:
        try:
            file_handler = logging.FileHandler(options.log_file, 'w', encoding='utf-8')
            file_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
            # When using a log file, always log at INFO level or higher to the file
            file_handler.setLevel(logging.INFO if not options.debug else logging.DEBUG)
            logger.addHandler(file_handler)
            
            # In quiet mode with a log file, redirect everything to the log file
            if options.quiet:
                # Remove all filters from the file handler to ensure it gets all messages
                for f in file_handler.filters:
                    file_handler.removeFilter(f)
        except Exception as e:
            logger.error(f"Failed to create log file: {e}")

def parse_arguments() -> CommandLineOptions:
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
        "--log-file", "-l", type=str,
        help="Write log output to FILE instead of stderr"
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
        "--quiet", "-Q", action="store_true",
        help="Quiet mode: only output errors, no status messages"
    )
    parser.add_argument(
        "--max-size", "-m", type=int, default=10,
        help="Maximum file size to embed in MB (default: 10)"
    )
    parser.add_argument(
        "--max-width", "-W", type=int,
        help="Maximum width for images in pixels. Images will be scaled down to fit if necessary."
    )
    parser.add_argument(
        "--max-height", "-H", type=int,
        help="Maximum height for images in pixels. Images will be scaled down to fit if necessary."
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
    
    # If path is not specified but input file is, use the input file's directory as base path.
    base_path = args.path
    if not base_path and args.input_file:
        base_path = os.path.dirname(os.path.abspath(args.input_file))
        logger.debug(f"Using input file directory as base path: {base_path}")
    
    options = CommandLineOptions(
        debug=args.debug,
        verbose=args.verbose,
        quiet=args.quiet,
        yarle_mode=args.yarle,
        input_file=args.input_file,
        output_file=args.output_file,
        log_file=args.log_file,
        base_path=base_path,
        quality_scale=args.quality,
        max_file_size_mb=args.max_size,
        max_width=args.max_width,
        max_height=args.max_height
    )
    
    return options

def format_file_size(size_bytes: int) -> str:
    """
    Format a file size in human-readable form.
    """
    units = ["B", "KB", "MB", "GB", "TB"]
    if size_bytes == 0:
        return "0 B"
    unit_index = 0
    while size_bytes >= 1024 and unit_index < len(units) - 1:
        size_bytes /= 1024.0
        unit_index += 1
    return f"{size_bytes:.1f} {units[unit_index]}"

def get_mime_type(url: str) -> str:
    """
    Determine the MIME type from a URL.
    """
    _, ext = os.path.splitext(url)
    if not ext:
        return "image/jpeg"
    ext = ext.lower()
    if ext in ['.jpg', '.jpeg']:
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
    mime_type, _ = mimetypes.guess_type(url)
    if mime_type and mime_type.startswith('image/'):
        return mime_type
    return "image/jpeg"

def is_video_file(data: bytes) -> bool:
    """
    Check if the file data appears to be a video.
    """
    if len(data) < 12:
        return False
    if data[0:4] == b'\x00\x00\x01\xBA':
        return True
    if data[0:4] == b'\x1A\x45\xDF\xA3':
        return True
    if data[4:8] == b'ftyp':
        return True
    if data[0:4] == b'RIFF' and data[8:12] == b'AVI ':
        return True
    if data[0:3] == b'FLV':
        return True
    return False

def calculate_jpeg_quality(file_size_bytes: int, quality_scale: int) -> int:
    """
    Calculate the JPEG quality level based on file size and quality scale.
    """
    SIZE_1KB = 1 * 1024
    SIZE_5KB = 5 * 1024
    SIZE_20KB = 20 * 1024
    SIZE_50KB = 50 * 1024
    SIZE_100KB = 100 * 1024
    SIZE_200KB = 200 * 1024
    quality_table = [
        [100, 100, 100, 100, 100, 100, 100, 100, 100],
        [30, 45, 60, 75, 90, 92, 94, 96, 98],
        [25, 37, 49, 60, 70, 77, 83, 89, 95],
        [20, 28, 36, 43, 50, 60, 70, 80, 90],
        [15, 22, 28, 34, 40, 52, 63, 74, 85],
        [12, 16, 19, 22, 25, 40, 53, 67, 80],
        [10, 12, 14, 16, 18, 33, 47, 61, 75]
    ]
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
        row_index = 6
    quality_scale_index = quality_scale - 1
    return quality_table[row_index][quality_scale_index]

def compress_to_jpeg(input_data: bytes, quality_scale: int, url: str = "", max_width: Optional[int] = None, max_height: Optional[int] = None) -> Tuple[Optional[bytes], int, int, int]:
    """
    Compress image data to JPEG format.
    """
    original_size = len(input_data)
    jpeg_quality = calculate_jpeg_quality(original_size, quality_scale)
    
    if jpeg_quality == 100 and original_size <= 1024 and not max_width and not max_height:
        logger.debug(f"Small image ({original_size} bytes): no compression needed")
        return input_data, jpeg_quality, original_size, original_size
        
    try:
        if url.lower().endswith('.svg'):
            if not SVG_SUPPORT:
                logger.error("SVG support not available. Please install svglib and reportlab: pip install svglib reportlab")
                return None, 0, original_size, 0
            drawing = svg2rlg(io.BytesIO(input_data))
            if not drawing:
                logger.error(f"Failed to convert SVG to drawing: {url}")
                return None, 0, original_size, 0
            # Convert the drawing to PNG data using drawToString.
            png_data = renderPM.drawToString(drawing, fmt="PNG")
            img = Image.open(io.BytesIO(png_data))
        else:
            img = Image.open(io.BytesIO(input_data))
        
        # Resize image if max dimensions are specified
        if max_width or max_height:
            original_width, original_height = img.size
            new_width, new_height = original_width, original_height
            scale_factor = 1.0
            
            # Calculate scale factor for width if needed
            if max_width and original_width > max_width:
                width_scale = max_width / original_width
                if width_scale < scale_factor:
                    scale_factor = width_scale
            
            # Calculate scale factor for height if needed
            if max_height and original_height > max_height:
                height_scale = max_height / original_height
                if height_scale < scale_factor:
                    scale_factor = height_scale
            
            # Apply scaling if needed
            if scale_factor < 1.0:
                new_width = int(original_width * scale_factor)
                new_height = int(original_height * scale_factor)
                logger.debug(f"Resizing image from {original_width}x{original_height} to {new_width}x{new_height}")
                img = img.resize((new_width, new_height), Image.LANCZOS)
        
        output_buffer = io.BytesIO()
        
        # Convert palette images (mode P) to RGB
        if img.mode == 'P':
            img = img.convert('RGB')
        # Handle images with transparency
        elif img.mode in ('RGBA', 'LA') or 'transparency' in img.info:
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[3])
            else:
                background.paste(img, mask=img.convert('RGBA').split()[3])
            img = background
        
        img.save(output_buffer, format='JPEG', quality=jpeg_quality, optimize=True)
        output_data = output_buffer.getvalue()
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
    
    Supports both:
      - Standard markdown images: ![alt text](url)
      - Obsidian-style images: ![[url]] (with optional dimension info via a pipe)
    """
    # First try to find Obsidian-style images
    matches = []
    obsidian_pattern = re.compile(r'!\[\[(?P<url>.*?)\]\]')
    
    for match in obsidian_pattern.finditer(markdown):
        position = match.start()
        match_text = match.group(0)
        url = match.group("url")
        alt_text = ""
        matches.append(ImageMatch(match_text, alt_text, url, position, len(match_text)))
    
    # Then find standard markdown images, being careful with URLs containing parentheses
    pos = 0
    while pos < len(markdown):
        # Find the start of a markdown image
        start_pos = markdown.find("![", pos)
        if start_pos == -1:
            break
            
        # Find the end of the alt text
        alt_end = markdown.find("](", start_pos)
        if alt_end == -1:
            pos = start_pos + 2
            continue
            
        # Extract alt text
        alt_text = markdown[start_pos + 2:alt_end]
        
        # Find the end of the URL by finding the matching closing parenthesis
        # We need to handle nested parentheses in the URL
        url_start = alt_end + 2
        url_end = -1
        paren_count = 1
        
        for i in range(url_start, len(markdown)):
            if markdown[i] == '(':
                paren_count += 1
            elif markdown[i] == ')':
                paren_count -= 1
                if paren_count == 0:
                    url_end = i
                    break
                    
        if url_end == -1:
            pos = start_pos + 2
            continue
            
        url = markdown[url_start:url_end]
        
        # Skip already embedded images
        if url.startswith("data:image"):
            pos = url_end + 1
            continue
            
        match_text = markdown[start_pos:url_end + 1]
        matches.append(ImageMatch(match_text, alt_text, url, start_pos, len(match_text)))
        
        pos = url_end + 1
        
    return matches

def resolve_file_path(path: str, base_path: str) -> str:
    """
    Attempt to resolve a local file path.
    """
    clean_path = path.rstrip('/\\"\' \t\r\n')
    
    # URL decode the path to handle %20 and other encoded characters
    try:
        import urllib.parse
        decoded_path = urllib.parse.unquote(clean_path)
        logger.debug(f"URL decoded path: {clean_path} -> {decoded_path}")
        clean_path = decoded_path
    except Exception as e:
        logger.debug(f"Error decoding URL: {e}")
    
    if os.path.isfile(clean_path):
        return clean_path
        
    if base_path:
        base_path = base_path.rstrip('/\\"\' \t\r\n')
        relative_path = clean_path
        if relative_path.startswith("./"):
            relative_path = relative_path[2:]
        full_path = os.path.join(base_path, relative_path)
        if os.path.isfile(full_path):
            return full_path
            
    return ""

def is_embedded_image(url: str) -> bool:
    """
    Check if a URL is already an embedded image.
    """
    return url.startswith("data:image/") or url.startswith("data:image%2F")

def split_on_unescaped_pipe(text: str) -> Tuple[str, Optional[str]]:
    """
    Splits the given text at the first unescaped pipe.
    
    Returns a tuple (before, after) where 'after' is None if no unescaped pipe is found.
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
    """
    url = match.url
    is_local_file = False
    image_data = None

    logger.debug(f"Processing image: {url}")

    url, _ = split_on_unescaped_pipe(url)
    url = url.strip()

    if is_embedded_image(url):
        logger.info("Preserving already embedded image.")
        return match.original_text

    if options.yarle_mode and not url.startswith(("http://", "https://")):
        if "./_resources/" in url or ".resources/" in url:
            logger.debug(f"Handling Yarle resource path: {url}")
            resolved_path = resolve_file_path(url, options.base_path)
            if resolved_path:
                url = resolved_path
                logger.debug(f"Resolved to: {url}")

    if not url.startswith(("http://", "https://")):
        is_local_file = True
        if not os.path.isfile(url):
            logger.debug(f"File not found at exact path: {url}")
            resolved_path = resolve_file_path(url, options.base_path)
            if resolved_path:
                url = resolved_path
                logger.debug(f"Resolved to: {url}")
            else:
                logger.debug(f"Failed to resolve local file: {url}")
                # Try to create directory listing to help diagnose the issue
                try:
                    dir_path = os.path.dirname(url) or '.'
                    if os.path.exists(dir_path):
                        files = os.listdir(dir_path)
                        logger.debug(f"Files in directory {dir_path}: {files[:10]}{' and more...' if len(files) > 10 else ''}")
                except Exception as dir_err:
                    logger.debug(f"Error listing directory: {dir_err}")
                
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

    if is_video_file(image_data):
        logger.info(f"Skipping video file: {url}")
        stats["non_embedded_resources"].add(url)
        return match.original_text

    mime_type = get_mime_type(url)
    if not mime_type:
        logger.debug(f"Unsupported file type: {url}")
        stats["non_embedded_resources"].add(url)
        return match.original_text

    compressed_data, jpeg_quality, original_size, compressed_size = compress_to_jpeg(image_data, options.quality_scale, url, options.max_width, options.max_height)
    if not compressed_data:
        logger.debug(f"Image compression failed: {url}")
        stats["non_embedded_resources"].add(url)
        return match.original_text

    stats["total_image_size"] += original_size
    stats["total_compressed_size"] += compressed_size

    logger.info(
        f"Embedding [{url}](JPEG quality {jpeg_quality}%): {format_file_size(original_size)} -> {format_file_size(compressed_size)}"
    )

    base64_data = base64.b64encode(compressed_data).decode('ascii')
    final_size = len(base64_data) + MARKDOWN_IMAGE_OVERHEAD
    max_file_size_bytes = options.max_file_size_mb * 1024 * 1024
    if final_size > max_file_size_bytes:
        logger.debug(
            f"Base64 encoded image too large: {url} ({format_file_size(final_size)}) > {format_file_size(max_file_size_bytes)}"
        )
        stats["non_embedded_resources"].add(url)
        return match.original_text

    alt_text = match.alt_text
    alt_text, dimensions = split_on_unescaped_pipe(alt_text)
    alt_text = alt_text.replace('\\', '')
    
    if dimensions:
        dimensions = dimensions.replace(r'\|', '|')
    else:
        dimensions = ""

    embedded_image = f"![{alt_text}{dimensions}](data:{mime_type};base64,{base64_data})"

    make_clickable = False
    link_target = ""
    if not is_local_file and url.startswith(("http://", "https://")):
        make_clickable = True
        link_target = url.replace('\\', '')
    elif match.alt_text.startswith(("http://", "https://")):
        make_clickable = True
        link_target = match.alt_text.replace('\\', '')

    if make_clickable:
        link_target, _ = split_on_unescaped_pipe(link_target)
        link_target = link_target.replace('\\', '')
        return f"[![{alt_text}{dimensions}](data:{mime_type};base64,{base64_data})]({link_target})"
    else:
        return embedded_image

def process_markdown(markdown: str, options: CommandLineOptions) -> Tuple[str, dict]:
    """
    Process markdown text and embed images.
    """
    original_markdown_size = len(markdown)

    stats = {
        "total_image_size": 0,
        "total_compressed_size": 0,
        "total_output_size": 0,
        "images_processed": 0,
        "skipped_images": 0,
        "non_embedded_resources": set()
    }

    matches = find_image_links(markdown)
    logger.info(f"Found {len(matches)} image links in markdown")

    result = []
    last_pos = 0
    for match in matches:
        if match.position > last_pos:
            result.append(markdown[last_pos:match.position])
        logger.debug(f"Processing image match at position {match.position}")
        embedded_image = process_image_match(match, options, stats)
        result.append(embedded_image)
        last_pos = match.position + match.length

        if embedded_image != match.original_text:
            stats["images_processed"] += 1
        else:
            stats["skipped_images"] += 1

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

def main() -> int:
    """Main entry point for the application."""
    options = parse_arguments()
    
    # Configure logging based on options
    configure_logging(options)
    
    try:
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
            try:
                input_markdown = sys.stdin.read()
                logger.info("Read input from stdin")
            except Exception as e:
                logger.error(f"Error reading from stdin: {e}")
                return 1
            
        logger.info("Processing markdown...")
        output_markdown, stats = process_markdown(input_markdown, options)
        
        try:
            if options.output_file:
                with open(options.output_file, 'w', encoding='utf-8') as f:
                    f.write(output_markdown)
                logger.info(f"Wrote output to file: {options.output_file}")
            else:
                sys.stdout.write(output_markdown)
                sys.stdout.flush()
                logger.info("Wrote output to stdout")
        except Exception as e:
            logger.error(f"Error writing output: {e}")
            return 1
            
        if stats["images_processed"] > 0 and not options.quiet:
            logger.info(f"{stats['images_processed']} images processed")
            
        if stats["non_embedded_resources"] and not options.quiet:
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
    