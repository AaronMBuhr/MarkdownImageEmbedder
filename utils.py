"""
Utility functions for MarkdownImageEmbedder.
"""

import os
import sys
from typing import Optional, Union


def format_file_size(size_bytes: int, decimals: int = 1) -> str:
    """
    Format a file size in human-readable form.
    
    Args:
        size_bytes: The size in bytes
        decimals: Number of decimal places to display
        
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
        
    # Format with specified decimal places
    return f"{size_bytes:.{decimals}f} {units[unit_index]}"


def is_video_file_by_extension(path: str) -> bool:
    """
    Check if a file appears to be a video based on its extension.
    
    Args:
        path: Path to the file
        
    Returns:
        bool: True if the file has a video extension, False otherwise
    """
    video_extensions = {
        '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv', 
        '.mpeg', '.mpg', '.m4v', '.3gp', '.3g2', '.ogv', '.ts'
    }
    
    _, ext = os.path.splitext(path)
    return ext.lower() in video_extensions


def get_temp_file_path(prefix: str = "mdie_", suffix: str = "") -> str:
    """
    Generate a path for a temporary file.
    
    Args:
        prefix: Prefix for the temporary file name
        suffix: Suffix for the temporary file name (extension)
        
    Returns:
        str: Path to a temporary file
    """
    import tempfile
    
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
    os.close(fd)
    return path


def read_stdin_or_file(file_path: Optional[str] = None) -> str:
    """
    Read content from stdin or a file.
    
    Args:
        file_path: Path to a file (optional, uses stdin if None)
        
    Returns:
        str: The content read from stdin or the file
    """
    if file_path:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            raise RuntimeError(f"Error reading input file: {e}")
    else:
        try:
            return sys.stdin.read()
        except Exception as e:
            raise RuntimeError(f"Error reading from stdin: {e}")


def write_stdout_or_file(content: str, file_path: Optional[str] = None) -> None:
    """
    Write content to stdout or a file.
    
    Args:
        content: The content to write
        file_path: Path to a file (optional, uses stdout if None)
    """
    if file_path:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            raise RuntimeError(f"Error writing to output file: {e}")
    else:
        try:
            sys.stdout.write(content)
        except Exception as e:
            raise RuntimeError(f"Error writing to stdout: {e}")
