"""
This module is the entry point for the markdown-image-embedder package.
It re-exports the necessary elements for use when installed as a package.
"""

# Use absolute imports to prevent the relative import issue
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import directly from the files
from base64_encoder import Base64Encoder
from cli_parser import CommandLineParser, CommandLineOptions
from http_client import HttpClient, create_http_client
from image_processor import ImageProcessor
from logger_setup import LoggerSetup
from markdown_processor import MarkdownProcessor, ImageMatch

# Import the main function from __main__
from __main__ import main
