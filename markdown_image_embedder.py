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
import glob  # Added for wildcard expansion
import shutil # Added for backup functionality
import warnings  # Added for warning capture
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

import requests
from PIL import Image

# Set up logging early so we can log any import issues.
logging.basicConfig(format='%(levelname)s: %(message)s', stream=sys.stderr)
logger = logging.getLogger('markdown-image-embedder')
logger.setLevel(logging.INFO)

# Create a custom warning handler that redirects warnings to our logger
def warning_to_logger(message, category, filename, lineno, file=None, line=None):
    """Send warnings to our logger with prefix format."""
    warning_message = f"{filename}:{lineno}: {category.__name__}: {message}"
    # If we're in the middle of processing a file, we'll add the prefix
    current_file = getattr(warning_to_logger, 'current_file', None)
    if current_file:
        print(f"markdown_image_embedder error processing file: {os.path.basename(current_file)}", file=sys.stderr)
    print(warning_message, file=sys.stderr)
    logger.warning(warning_message)

# Store the current file being processed in the warning handler
warning_to_logger.current_file = None

# Redirect warnings to our custom handler
warnings.showwarning = warning_to_logger

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
    summary: bool = False
    backup: bool = False
    overwrite: bool = False
    yarle_mode: bool = False
    input_files: List[str] = None
    output_file: Optional[str] = None
    log_file: Optional[str] = None
    base_path: str = ""
    quality_scale: int = 5  # Default 5 (1-9 scale, lower = higher quality)
    max_file_size_mb: int = 10  # Maximum size for embedded files in MB
    max_width: Optional[int] = None  # Maximum width for images in pixels
    max_height: Optional[int] = None  # Maximum height for images in pixels
    current_file: Optional[str] = None  # Current file being processed (for error context)

@dataclass
class ImageMatch:
    """Represents a matched image in markdown."""
    original_text: str  # Original markdown text
    alt_text: str       # Alt text for the image
    url: str            # URL or file path to the image
    position: int       # Position in the original markdown
    length: int         # Length of the match
    ref_id: Optional[str] = None  # Reference label if this is a reference-style image
    style: str = "inline"         # 'inline', 'reference', or 'obsidian'

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
    # Always set base logger level to DEBUG to allow all messages to reach all handlers
    # Individual handlers will filter based on their own levels
    logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers to avoid duplication
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()  # Ensure files are closed
    
    # Add file handler if log file specified - always gets verbose (INFO) or debug output
    if options.log_file:
        try:
            file_handler = logging.FileHandler(options.log_file, 'w', encoding='utf-8')
            file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s: %(message)s'))
            # Log file always gets minimum INFO level (verbose output), or DEBUG if requested
            if options.debug:
                file_handler.setLevel(logging.DEBUG)
            else:
                file_handler.setLevel(logging.INFO)  # Verbose output for log files by default
            logger.addHandler(file_handler)
            # Use file_handler directly to log startup message to avoid console output
            startup_msg = f"File logging started at level {logging.getLevelName(file_handler.level)}"
            file_record = logging.LogRecord(
                name=logger.name, level=logging.INFO, 
                pathname="", lineno=0, 
                msg=startup_msg, args=(), exc_info=None
            )
            file_handler.emit(file_record)
        except Exception as e:
            # Use print because logging might be unreliable
            print(f"FATAL: Failed to create log file '{options.log_file}': {e}", file=sys.stderr)
            # Continue with console only
            pass
            
    # Configure Console Handler (stderr) - will have different level than file handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))  # Simpler format for console
    
    # Determine writing_to_stdout based on options
    is_piped_stdin = not sys.stdin.isatty()
    writing_to_stdout = False  # Default to False
    if not options.input_files and is_piped_stdin and not options.output_file:
        # Input from stdin, output to stdout
        writing_to_stdout = True
    elif options.input_files and len(options.input_files) == 1 and not glob.has_magic(options.input_files[0]):
        # Single specific input file provided
        # Check if it truly resolves to one file and no output/backup/overwrite is set
        try:
            if len(glob.glob(options.input_files[0], recursive=True)) == 1:
                if not options.output_file and not options.backup and not options.overwrite:
                    writing_to_stdout = True
        except Exception:
            pass  # Ignore glob errors for this check
            
    # Configure console output level based on user options
    if writing_to_stdout:
        # If writing markdown to stdout, silence console messages completely
        console_handler.setLevel(logging.CRITICAL + 1)  # Set level higher than critical
    elif options.quiet:
        console_handler.setLevel(logging.ERROR)  # Only show ERROR and CRITICAL
    elif options.verbose:
        console_handler.setLevel(logging.INFO)  # Show INFO (verbose per-image output)
    elif options.debug:
        console_handler.setLevel(logging.DEBUG)  # Show DEBUG messages
    else:
        # Default Concise Summary Mode - suppress detailed processing messages
        # The actual summary will be printed separately at the end
        console_handler.setLevel(logging.ERROR)  # Only show errors during processing

    logger.addHandler(console_handler)
    
    # Ensure logger propagation is disabled to prevent duplicates
    logger.propagate = False

def parse_arguments() -> CommandLineOptions:
    """Parse command line arguments, separating known options from input files."""
    parser = argparse.ArgumentParser(
        description="Embed images in markdown files as base64 encoded data URLs.",
        # Prevent argparse from exiting on its own for unrecognized args
        # add_help=False # We might add our own help processing later if needed
    )

    # --- Define Known Options --- 
    # Input/Output Options (Remove --input-files)
    # parser.add_argument(
    #     "--input-files", "-i", type=str, nargs='+',
    #     help="One or more input markdown files or patterns (wildcards allowed). If omitted, reads from stdin."
    # )
    parser.add_argument(
        "--output-file", "-o", type=str,
        help="Write output to FILE instead of stdout. Incompatible with multiple inputs or --backup/--overwrite."
    )
    backup_overwrite_group = parser.add_mutually_exclusive_group()
    backup_overwrite_group.add_argument(
        "--backup", "-b", action="store_true",
        help="Create a backup (.bak) of the original file before overwriting. Incompatible with -o."
    )
    backup_overwrite_group.add_argument(
        "--overwrite", action="store_true", # No short option for safety
        help="Overwrite the original input file(s). Required if using multiple inputs without --backup. Incompatible with -o."
    )

    # Logging & Reporting
    parser.add_argument(
        "--log-file", "-l", type=str,
        help="Write log output to FILE instead of stderr"
    )
    # Console Output Control Group (Mutually Exclusive)
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "--quiet", "-Q", action="store_true",
        help="Quiet console output: only show critical errors on stderr."
    )
    verbosity_group.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose console output: show detailed per-image processing info on stderr."
    )
    verbosity_group.add_argument(
        "--debug", "-d", action="store_true",
        help="Debug console output: show detailed debug messages on stderr."
    )
    # Note: A concise summary is the default console output if none of the above are specified
    # and if output is not going to stdout.

    # Processing Options
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
        "--max-width", "-W", type=int,
        help="Maximum width for images in pixels. Images will be scaled down to fit if necessary."
    )
    parser.add_argument(
        "--max-height", "-H", type=int,
        help="Maximum height for images in pixels. Images will be scaled down to fit if necessary."
    )
    parser.add_argument(
        "--path", "-p", type=str, default="",
        help="Base path for resolving relative file paths (defaults to CWD if multiple/wildcard inputs, else input file's directory)"
    )

    # --- Parse Known Args & Separate Input Files --- 
    args, unknown_args = parser.parse_known_args()

    input_files = []
    potential_errors = []
    for arg in unknown_args:
        # Treat non-option arguments as input files/patterns
        if not arg.startswith('-'):
            input_files.append(arg)
        # Allow --log-file added by batch script
        elif arg == '--log-file':
            # Find its value (the next argument)
            try:
                log_file_index = unknown_args.index('--log-file')
                if log_file_index + 1 < len(unknown_args):
                     args.log_file = unknown_args[log_file_index + 1]
                     # Remove --log-file and its value so they aren't treated as errors
                     # Process removal carefully to avoid index issues
                     del unknown_args[log_file_index:log_file_index+2]
                else:
                     potential_errors.append(f"argument --log-file: expected one argument")
            except ValueError:
                 pass # Should not happen if found, but handle gracefully
            except Exception as e: # Catch other potential issues
                 potential_errors.append(f"Error processing --log-file argument: {e}")
        else:
            # Any other unknown arg starting with '-' is an error
            potential_errors.append(arg)

    if potential_errors:
         parser.error(f"unrecognized arguments: {' '.join(potential_errors)}")

    # --- Validation based on separated inputs --- 
    # Check if stdin is being used (no explicit files and stdin is not a tty)
    is_piped_stdin = not sys.stdin.isatty()
    is_stdin_input = not input_files and is_piped_stdin
    
    if not input_files and not is_stdin_input:
        parser.error("No input files specified and no data piped via stdin.")
    elif not input_files and is_stdin_input and (args.backup or args.overwrite):
        # Cannot use backup/overwrite with stdin
        parser.error("--backup or --overwrite cannot be used with stdin input.")
        
    is_multi_input = len(input_files) > 1
    # Use glob logic here for more robust wildcard detection
    has_wildcards = False
    actual_input_files_for_check = []
    if input_files:
        try:
            # Expand potential wildcards ONLY for the validation check
            # The actual expansion happens later in main()
            temp_expanded = []
            for pattern in input_files:
                 # Use glob.has_magic to check for actual wildcard characters
                 if glob.has_magic(pattern):
                     has_wildcards = True
                     # Attempt expansion to see if it matches multiple files
                     matches = glob.glob(pattern, recursive=True)
                     if len(matches) > 1:
                         is_multi_input = True # Treat wildcard matching multiple as multi-input
                     temp_expanded.extend(matches)
                 else:
                     temp_expanded.append(pattern)
            actual_input_files_for_check = temp_expanded
            if len(actual_input_files_for_check) > 1:
                 is_multi_input = True
        except Exception as e:
            logger.warning(f"Could not reliably check for wildcards due to error: {e}")
            # Be conservative: assume wildcards if any pattern contains wildcard chars
            has_wildcards = any(glob.has_magic(p) for p in input_files)
            if len(input_files) > 1:
                 is_multi_input = True
                 
    # Now perform validation using potentially updated is_multi_input/has_wildcards
    if (is_multi_input or has_wildcards):
        if not args.backup and not args.overwrite and not args.output_file:
            # Allow processing multiple files only if backup, overwrite, or a single aggregate output file is specified
            parser.error("Multiple input files or wildcards require either --backup (-b), --overwrite, or --output-file (-o).")
    elif input_files: # Single input file specified (len == 1 and no wildcards detected)
         if args.backup and args.output_file:
             parser.error("--backup (-b) cannot be used with --output-file (-o).")
         if args.overwrite and args.output_file:
             parser.error("--overwrite cannot be used with --output-file (-o).")
    # No specific validation needed for stdin + output_file case here

    # --- Base Path Logic --- 
    base_path = args.path
    if not base_path:
        if input_files and len(input_files) == 1 and not has_wildcards:
            # Single, specific input file
            try:
                 # Use abspath to handle relative input paths correctly
                abs_input_path = os.path.abspath(input_files[0])
                if os.path.isfile(abs_input_path): # Check if it's a file before getting dirname
                    base_path = os.path.dirname(abs_input_path)
                    logger.debug(f"Using input file directory as base path: {base_path}")
                else:
                    # If the single input file doesn't exist yet, default to CWD
                    base_path = os.getcwd()
                    logger.debug(f"Single input file not found, using CWD as base path: {base_path}")
            except Exception as e:
                 logger.warning(f"Could not determine directory for input file {input_files[0]}, using CWD as base path. Error: {e}")
                 base_path = os.getcwd()
        else:
            # Stdin, multiple inputs, or wildcards: default base_path is current working directory
            base_path = os.getcwd()
            logger.debug(f"Using current working directory as base path: {base_path}")
    else:
         # If -p is provided, always use it and make it absolute
         base_path = os.path.abspath(base_path)
         logger.debug(f"Using specified base path: {base_path}")

    # --- Populate Options Dataclass --- 
    options = CommandLineOptions(
        debug=args.debug,
        quiet=args.quiet,
        verbose=args.verbose,
        backup=args.backup,
        overwrite=args.overwrite,
        yarle_mode=args.yarle,
        input_files=input_files, # Use the separated list
        output_file=args.output_file,
        log_file=args.log_file, # Already populated from unknown_args or None
        base_path=base_path,
        quality_scale=args.quality,
        max_file_size_mb=args.max_size,
        max_width=args.max_width,
        max_height=args.max_height,
        current_file=None  # Initialize to None, will be set during processing
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
      - Reference-style images:   ![alt text][ref]
      - Obsidian-style images:    ![[url]] (with optional dimension info via a pipe)
    """
    matches: List[ImageMatch] = []

    # --- Obsidian-style images: ![[path|optional stuff]] ---
    obsidian_pattern = re.compile(r'!\[\[(?P<url>.*?)\]\]')
    for m in obsidian_pattern.finditer(markdown):
        position = m.start()
        match_text = m.group(0)
        url = m.group("url")
        alt_text = ""
        matches.append(ImageMatch(
            match_text,
            alt_text,
            url,
            position,
            len(match_text),
            ref_id=None,
            style="obsidian",
        ))

    # --- Collect reference definitions: [id]: url ---
    ref_defs: dict[str, str] = {}
    ref_def_pattern = re.compile(r'^\[(?P<id>[^\]]+)\]:\s+(?P<url>\S+)', re.MULTILINE)
    for m in ref_def_pattern.finditer(markdown):
        ref_id = m.group("id")
        ref_url = m.group("url").strip()
        if ref_id and ref_url:
            ref_defs[ref_id] = ref_url

    # --- Standard inline images: ![alt](url) ---
    # This intentionally does NOT cross line boundaries, which avoids
    # accidentally treating complex constructs like:
    #   [![][img-ref] **Text**](https://example.com/article)
    # as a giant image whose "url" is the article page.
    inline_pattern = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\n]+)\)')
    for m in inline_pattern.finditer(markdown):
        url = m.group("url").strip()
        if url.startswith("data:image"):
            continue  # already embedded
        alt_text = m.group("alt")
        position = m.start()
        match_text = m.group(0)
        matches.append(ImageMatch(
            match_text,
            alt_text,
            url,
            position,
            len(match_text),
            ref_id=None,
            style="inline",
        ))

    # --- Reference-style images: ![alt][ref] ---
    ref_image_pattern = re.compile(r'!\[(?P<alt>[^\]]*)\]\[(?P<ref>[^\]]+)\]')
    for m in ref_image_pattern.finditer(markdown):
        ref_id = m.group("ref")
        url = ref_defs.get(ref_id)
        if not url:
            continue  # unresolved reference, skip
        url = url.strip()
        if url.startswith("data:image"):
            continue  # already embedded
        alt_text = m.group("alt")
        position = m.start()
        match_text = m.group(0)
        matches.append(ImageMatch(
            match_text,
            alt_text,
            url,
            position,
            len(match_text),
            ref_id=ref_id,
            style="reference",
        ))

    # Return matches in document order
    matches.sort(key=lambda m: m.position)
    return matches

def embed_image_data(match: ImageMatch, options: CommandLineOptions, stats: dict) -> Optional[str]:
    """
    Download/resolve, compress and base64‑encode image data for a single match.
    Returns the full data URL string, or None if embedding should be skipped.
    """
    url = match.url
    is_local_file = False
    image_data = None
    current_file = getattr(options, 'current_file', None)  # Get current file context if available

    logger.debug(f"Processing image for embedding: {url}")

    # Strip any dimension suffix after an unescaped pipe
    url, _ = split_on_unescaped_pipe(url)
    url = url.strip()

    if is_embedded_image(url):
        logger.debug("Image already embedded, skipping.")
        return None

    if options.yarle_mode and not url.startswith(("http://", "https://")):
        if "./_resources/" in url or ".resources/" in url:
            logger.debug(f"Handling Yarle resource path: {url}")
            resolved_path = resolve_file_path(url, options.base_path)
            if resolved_path:
                url = resolved_path
                logger.debug(f"Resolved to: {url}")

    # Resolve local vs remote
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
                        logger.debug(
                            f"Files in directory {dir_path}: "
                            f"{files[:10]}{' and more...' if len(files) > 10 else ''}"
                        )
                except Exception as dir_err:
                    logger.debug(f"Error listing directory: {dir_err}")
                
                stats["non_embedded_resources"].add(url)
                return None
        try:
            with open(url, "rb") as f:
                image_data = f.read()
        except Exception as e:
            err_msg = f"Error reading local file: {url} - {e}"
            if current_file:
                log_error_with_prefix(err_msg, os.path.basename(current_file))
            else:
                logger.error(err_msg)
            stats["non_embedded_resources"].add(url)
            return None
    else:
        image_data = download_image(url)
        if not image_data:
            logger.debug(f"Failed to download image: {url}")
            stats["non_embedded_resources"].add(url)
            return None

    if is_video_file(image_data):
        logger.info(f"Skipping video file: {url}")
        stats["non_embedded_resources"].add(url)
        return None

    mime_type = get_mime_type(url)
    if not mime_type:
        logger.debug(f"Unsupported file type: {url}")
        stats["non_embedded_resources"].add(url)
        return None

    compressed_data, jpeg_quality, original_size, compressed_size = compress_to_jpeg(
        image_data,
        options.quality_scale,
        url,
        options.max_width,
        options.max_height,
    )
    if not compressed_data:
        logger.debug(f"Image compression failed: {url}")
        stats["non_embedded_resources"].add(url)
        return None

    stats["total_image_size"] += original_size
    stats["total_compressed_size"] += compressed_size

    # Log detailed size info at INFO level (will go to file always, console if -v or -d)
    logger.info(
        f"Embedding [{url}](JPEG quality {jpeg_quality}%): "
        f"{format_file_size(original_size)} -> {format_file_size(compressed_size)}"
    )

    base64_data = base64.b64encode(compressed_data).decode('ascii')
    final_size = len(base64_data) + MARKDOWN_IMAGE_OVERHEAD
    max_file_size_bytes = options.max_file_size_mb * 1024 * 1024
    if final_size > max_file_size_bytes:
        logger.debug(
            f"Base64 encoded image too large: {url} "
            f"({format_file_size(final_size)}) > {format_file_size(max_file_size_bytes)}"
        )
        stats["non_embedded_resources"].add(url)
        return None

    data_url = f"data:{mime_type};base64,{base64_data}"
    return data_url

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

def log_error_with_prefix(message, filename=None):
    """
    Log error with standard prefix to both console and log file.
    Console error has specific prefix format.
    """
    # Full message goes to log file via normal logging
    logger.error(message)
    
    # Console gets prefixed message to stderr
    if filename:
        prefix = f"markdown_image_embedder error processing file: {filename}"
        print(f"{prefix}", file=sys.stderr)
    
    # Print the actual error message
    print(message, file=sys.stderr)

def process_image_match(match: ImageMatch, options: CommandLineOptions, stats: dict) -> str:
    """
    Process a single image match and return the embedded markdown.
    """
    url = match.url
    is_local_file = False
    image_data = None
    current_file = getattr(options, 'current_file', None)  # Get current file context if available

    logger.debug(f"Processing image: {url}")

    url, _ = split_on_unescaped_pipe(url)
    url = url.strip()

    if is_embedded_image(url):
        logger.debug("Preserving already embedded image.")
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
            err_msg = f"Error reading local file: {url} - {e}"
            if current_file:
                log_error_with_prefix(err_msg, os.path.basename(current_file))
            else:
                logger.error(err_msg)
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

    # Log detailed size info at INFO level (will go to file always, console if -v or -d)
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

def process_markdown(markdown: str, options: CommandLineOptions, current_file_path: Optional[str] = None) -> Tuple[str, dict]:
    """
    Process markdown text and embed images.
    Args:
        markdown: The markdown content to process.
        options: The command line options.
        current_file_path: The path to the current file being processed (used for logging context).
    Returns:
        A tuple containing the processed markdown and a dictionary of statistics.
    """
    original_markdown_size = len(markdown)
    # Use DEBUG level for context message, as it's not needed in normal verbose output
    file_context = f" for file: {current_file_path}" if current_file_path else " for stdin"
    logger.debug(f"Processing markdown{file_context}, original size: {original_markdown_size} bytes")

    # Store current file path in options for error context
    temp_options = options
    if current_file_path:
        temp_options.current_file = current_file_path

    stats = {
        "total_image_size": 0,
        "total_compressed_size": 0,
        "total_output_size": 0,
        "images_processed": 0,
        "skipped_images": 0,
        "non_embedded_resources": set()
    }

    matches = find_image_links(markdown)
    # This is a key message, log at INFO level for log file and verbose console
    logger.info(f"Found {len(matches)} image links{file_context}") 

    # --- First pass: generate unique embedded data URLs ---
    key_to_embedded_id: dict[Tuple[str, str], str] = {}
    embedded_data_by_id: dict[str, str] = {}
    img_counter = 1

    for match in matches:
        # Canonical key: reference label when available, otherwise URL
        if getattr(match, "style", None) == "reference" and match.ref_id:
            key = ("ref", match.ref_id)
        else:
            key = ("url", match.url)

        if key in key_to_embedded_id:
            # Already processed this logical image
            continue

        data_url = embed_image_data(match, temp_options, stats)
        if not data_url:
            stats["skipped_images"] += 1
            continue

        embedded_id = f"mie-img-{img_counter}"
        img_counter += 1
        key_to_embedded_id[key] = embedded_id
        embedded_data_by_id[embedded_id] = data_url
        stats["images_processed"] += 1

    # --- Second pass: rebuild markdown body using reference IDs ---
    result_parts = []
    last_pos = 0

    for match in matches:
        if match.position > last_pos:
            result_parts.append(markdown[last_pos:match.position])

        if getattr(match, "style", None) == "reference" and match.ref_id:
            key = ("ref", match.ref_id)
        else:
            key = ("url", match.url)

        embedded_id = key_to_embedded_id.get(key)
        if not embedded_id:
            # No embedded data for this image; leave original intact
            result_parts.append(match.original_text)
        else:
            # Preserve any dimensions encoded in the alt text
            alt_text = match.alt_text or ""
            alt_main, dimensions = split_on_unescaped_pipe(alt_text)
            alt_main = alt_main.replace('\\', '')
            if dimensions:
                dimensions = dimensions.replace(r'\|', '|')
            else:
                dimensions = ""

            display_alt = f"{alt_main}{dimensions}"
            replacement = f"![{display_alt}][{embedded_id}]"
            result_parts.append(replacement)

        last_pos = match.position + match.length

    if last_pos < len(markdown):
        result_parts.append(markdown[last_pos:])

    body = ''.join(result_parts)

    # --- Append embedded image reference definitions at the end ---
    if embedded_data_by_id:
        # Ensure there's a blank line before our block
        body = body.rstrip() + "\n\n"
        body += "<!-- Embedded image data generated by markdown_image_embedder -->\n"
        for embedded_id, data_url in embedded_data_by_id.items():
            body += f"[{embedded_id}]: {data_url}\n"

    output = body
    stats["total_output_size"] = len(output)

    total_original_size = original_markdown_size + stats["total_image_size"]
    final_size = stats["total_output_size"]
    change_bytes = final_size - original_markdown_size # Change relative to original markdown only
    stats["change_bytes"] = change_bytes
    compression_ratio = (final_size / total_original_size * 100) if total_original_size > 0 else 0

    # Log detailed size info at INFO level (will go to file always, console if -v or -d)
    logger.info(
        f"Sizes{file_context}: Original MD={format_file_size(original_markdown_size)}, "
        f"Images Found={stats['images_processed']} ({format_file_size(stats['total_image_size'])}), "
        f"Final MD Size={format_file_size(final_size)} (Change: {format_file_size(change_bytes)}), "
        f"Overall Ratio={compression_ratio:.0f}%"
    )
    
    # Add key stats for summary reporting
    stats["input_md_size"] = original_markdown_size
    stats["output_md_size"] = final_size

    return output, stats

def main() -> int:
    """Main entry point for the application."""
    options = parse_arguments()
    
    # Configure logging just once, early in main
    configure_logging(options)
    
    # --- Initialization ---
    exit_code = 0
    processed_files_count = 0
    overall_non_embedded = set()
    overall_success_count = 0
    overall_error_count = 0
    processed_file_details = []  # List to hold (filename, status, msg, initial_size, final_size)

    # --- Determine Input Files ---
    files_to_process = []
    if options.input_files:
        logger.debug(f"Input patterns/files: {options.input_files}")
        # Create a human-readable description of input patterns for summary output
        input_desc = ' '.join(f'"{pattern}"' if ' ' in pattern else pattern 
                            for pattern in options.input_files)
        
        for pattern in options.input_files:
            try:
                expanded_files = glob.glob(pattern, recursive=True)  # Allow recursive globbing
                if not expanded_files:
                     # Use our error handler for no matches
                     log_error_with_prefix(f"Input pattern '{pattern}' did not match any files.")
                else:
                    files_to_process.extend(expanded_files)
            except Exception as e:
                log_error_with_prefix(f"Error expanding pattern '{pattern}': {e}")
                exit_code = 1
        # Remove duplicates and sort
        files_to_process = sorted(list(set(f for f in files_to_process if os.path.isfile(f))))
        if not files_to_process:
             log_error_with_prefix("No valid input files found after expanding patterns.")
             return 1  # Hard exit if no files match
        logger.info(f"Found {len(files_to_process)} files to process.")
    else:
        input_desc = "stdin"
        logger.info("Reading input from stdin...")
        # Intentionally leave files_to_process empty for stdin case

    # --- Processing Loop ---
    if files_to_process:
        is_first_output_write = bool(options.output_file)
        # Print header with clear description of what we're processing
        file_count = len(files_to_process)
        if file_count == 1:
            # For single file, use the actual filename with quotes if needed
            filename = os.path.basename(files_to_process[0])
            if ' ' in filename or '&' in filename:
                print(f"markdown_image_embedder processing 1 file: \"{filename}\"", file=sys.stderr)
            else:
                print(f"markdown_image_embedder processing 1 file: {filename}", file=sys.stderr)
        else:
            # For multiple files, use the original input pattern(s)
            print(f"markdown_image_embedder processing {file_count} files: {input_desc}", file=sys.stderr)
            
        for input_file in files_to_process:
            # Store details for final summary
            file_detail = {"filename": input_file, "status": "ERROR", "message": "", 
                           "initial_size": 0, "final_size": 0}
            # Set current file in the warning handler
            warning_to_logger.current_file = input_file
            # Log start of file processing at INFO level (console if -v/-d, always in log file)
            logger.info(f"--- Processing file: {input_file} ---") 
            try:
                # Log reading action at DEBUG level
                logger.debug(f"Reading file: {input_file}")
                with open(input_file, 'r', encoding='utf-8') as f:
                    input_markdown = f.read()
                file_detail["initial_size"] = len(input_markdown) # Store initial size

                output_markdown, stats = process_markdown(input_markdown, options, current_file_path=input_file)
                overall_non_embedded.update(stats["non_embedded_resources"])

                # Determine output action
                if options.output_file:
                    # Aggregate all processed files into a single output file.
                    # First file truncates/creates, subsequent files append.
                    logger.debug(f"Writing output to file: {options.output_file}") 
                    try:
                        mode = 'w' if is_first_output_write else 'a'
                        with open(options.output_file, mode, encoding='utf-8') as f:
                            f.write(output_markdown)
                        is_first_output_write = False
                        file_detail["status"] = "OK"
                        processed_files_count += 1
                    except Exception as e:
                        err_msg = f"Failed to write output file {options.output_file}: {e}"
                        log_error_with_prefix(err_msg, os.path.basename(input_file))
                        file_detail["message"] = f"write failed: {e}"
                        exit_code = 1
                elif options.backup:
                    backup_file = input_file + ".bak"
                    # Log backup action at DEBUG level (less critical than processing)
                    logger.debug(f"Creating backup: {backup_file}") 
                    try:
                        shutil.copy2(input_file, backup_file)
                        with open(input_file, 'w', encoding='utf-8') as f:
                            f.write(output_markdown)
                        # Log overwrite action at DEBUG level
                        logger.debug(f"Overwrote original file: {input_file}") 
                        file_detail["status"] = "OK"
                        processed_files_count += 1
                    except Exception as e:
                        err_msg = f"Failed to create backup or overwrite {input_file}: {e}"
                        log_error_with_prefix(err_msg, os.path.basename(input_file))
                        file_detail["message"] = f"backup/overwrite failed: {e}"
                        exit_code = 1
                elif options.overwrite:
                    # Log overwrite action at DEBUG level
                    logger.debug(f"Overwriting original file: {input_file}") 
                    try:
                        with open(input_file, 'w', encoding='utf-8') as f:
                            f.write(output_markdown)
                        file_detail["status"] = "OK"
                        processed_files_count += 1
                    except Exception as e:
                        err_msg = f"Failed to overwrite {input_file}: {e}"
                        log_error_with_prefix(err_msg, os.path.basename(input_file))
                        file_detail["message"] = f"overwrite failed: {e}"
                        exit_code = 1
                else:
                    # Single file, no backup/overwrite, no output file -> stdout
                    # Use logger.debug here as markdown is going to stdout
                    logger.debug("Writing output to stdout") 
                    # --- CRITICAL: Write ONLY markdown to stdout --- 
                    sys.stdout.write(output_markdown)
                    sys.stdout.flush()
                    # --- END CRITICAL SECTION --- 
                    file_detail["status"] = "OK"
                    processed_files_count += 1

                # Update final size for summary
                file_detail["final_size"] = stats.get("output_md_size", 0)

            except Exception as e:
                err_msg = f"Error processing file {input_file}: {e}"
                # Use our standardized error handler
                log_error_with_prefix(err_msg, os.path.basename(input_file))
                file_detail["message"] = f"Error: {e}"
                exit_code = 1
                if options.debug:
                    logger.exception(f"Stack trace for {input_file}:", exc_info=True)

            finally:
                # Reset the warning handler's current file
                warning_to_logger.current_file = None

            # Store results for this file
            processed_file_details.append(file_detail)
            if file_detail["status"] == "OK":
                 overall_success_count += 1
            else:
                 overall_error_count += 1

    else: # Process stdin
        stdin_detail = {"filename": "stdin", "status": "ERROR", "message": "",
                        "initial_size": 0, "final_size": 0}
        # Set current file in warning handler for stdin
        warning_to_logger.current_file = "stdin"
        try:
            # Log stdin actions at INFO level (always in log file, console only if -v/-d)
            logger.info("Reading markdown from stdin...") 
            input_markdown = sys.stdin.read()
            stdin_detail["initial_size"] = len(input_markdown)
            logger.info("Processing markdown from stdin...") 
            output_markdown, stats = process_markdown(input_markdown, options, current_file_path="stdin")
            overall_non_embedded.update(stats["non_embedded_resources"])
            stdin_detail["status"] = "OK"
            processed_files_count += 1

            # Determine output action for stdin
            if options.output_file:
                 # Log write action at DEBUG level
                 logger.debug(f"Writing output to file: {options.output_file}") 
                 try:
                     with open(options.output_file, 'w', encoding='utf-8') as f:
                         f.write(output_markdown)
                     stdin_detail["status"] = "OK"
                     processed_files_count += 1
                 except Exception as e:
                     err_msg = f"Failed to write output file {options.output_file}: {e}"
                     log_error_with_prefix(err_msg, "stdin")
                     stdin_detail["message"] = f"write failed: {e}"
                     exit_code = 1
            else:
                # Default for stdin is stdout
                # Use logger.debug here as markdown is going to stdout
                logger.debug("Writing output to stdout") 
                # --- CRITICAL: Write ONLY markdown to stdout --- 
                sys.stdout.write(output_markdown)
                sys.stdout.flush()
                # --- END CRITICAL SECTION --- 
                stdin_detail["status"] = "OK"
                processed_files_count += 1

            # Update final size for summary
            stdin_detail["final_size"] = stats.get("output_md_size", 0)

        except Exception as e:
            err_msg = f"Error processing stdin: {e}"
            # Use standardized error handler for stdin
            log_error_with_prefix(err_msg, "stdin")
            stdin_detail["message"] = f"Error: {e}"
            exit_code = 1
            if options.debug:
                logger.exception("Stack trace for stdin:", exc_info=True)

        finally:
            # Reset the warning handler's current file
            warning_to_logger.current_file = None

        # Store results for stdin
        processed_file_details.append(stdin_detail)
        if stdin_detail["status"] == "OK":
            overall_success_count += 1
        else:
            overall_error_count += 1

    # --- Final Reporting ---
    # Print concise summary to stderr if NOT writing to stdout and we're in normal mode
    # (not quiet, not verbose, not debug)
    is_piped_stdin = not sys.stdin.isatty()
    writing_to_stdout = False
    if not options.input_files and is_piped_stdin and not options.output_file:
        writing_to_stdout = True
    elif options.input_files and len(options.input_files) == 1 and not glob.has_magic(options.input_files[0]):
        try:
            if len(glob.glob(options.input_files[0], recursive=True)) == 1:
                if not options.output_file and not options.backup and not options.overwrite:
                    writing_to_stdout = True
        except Exception:
            pass
    
    if not options.quiet and not options.verbose and not options.debug and not writing_to_stdout: 
        total_processed = len(processed_file_details)
        # Construct input description
        input_desc = "stdin" if not files_to_process else ' '.join(options.input_files)
        if total_processed > 0:
            # Format the summary to match the expected output
            print(f"markdown_image_embedder processing {total_processed} files: {input_desc}", file=sys.stderr)
            
            # Print each file's result in the desired format
            for item in processed_file_details:
                 if item["status"] == "OK":
                     print(f"{os.path.basename(item['filename'])}: {format_file_size(item['initial_size'])} -> {format_file_size(item['final_size'])}", file=sys.stderr)
                 else:
                     print(f"{os.path.basename(item['filename'])}: {item['message']}", file=sys.stderr)
            
            # Print the done line with success/failure summary
            print(f"Done. {total_processed} files: {overall_success_count} success, {overall_error_count} failure(s)", file=sys.stderr)
        elif files_to_process: # Input files specified, but none were processed
             print(f"markdown_image_embedder attempted processing {len(files_to_process)} files: {input_desc}", file=sys.stderr)
             print(f"No files successfully processed. Check logs for failures.", file=sys.stderr)
             
    # Report non-embedded resources to log file always (not to console in normal/quiet mode)
    if overall_non_embedded: 
        # Use logger.info so it goes to log file and only appears in console if verbose/debug
        logger.info("\nThe following resources were referenced but not embedded (check paths/URLs):") 
        # Sort for consistent output
        for resource in sorted(list(overall_non_embedded)):
            logger.info(f"  {resource}")

    return exit_code

if __name__ == "__main__":
    sys.exit(main())
    