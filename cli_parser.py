"""
Command line argument parser for MarkdownImageEmbedder.
"""

import argparse
from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandLineOptions:
    """Holds the parsed command line options."""
    show_help: bool = False
    debug: bool = False
    verbose: bool = False
    yarle_mode: bool = False
    input_file: Optional[str] = None
    output_file: Optional[str] = None
    base_path: str = ""
    quality_scale: int = 5  # Default 5 (1-9 scale, lower = higher quality)
    max_file_size_mb: int = 10  # Maximum size for embedded files in MB


class CommandLineParser:
    """Parses command line arguments."""

    @staticmethod
    def parse(args: list[str]) -> CommandLineOptions:
        """
        Parse command line arguments.
        
        Args:
            args: Command line arguments
            
        Returns:
            CommandLineOptions: The parsed options
        """
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

        parsed_args = parser.parse_args(args)
        
        options = CommandLineOptions(
            debug=parsed_args.debug,
            verbose=parsed_args.verbose,
            yarle_mode=parsed_args.yarle,
            input_file=parsed_args.input_file,
            output_file=parsed_args.output_file,
            base_path=parsed_args.path,
            quality_scale=parsed_args.quality,
            max_file_size_mb=parsed_args.max_size
        )
        
        return options

    @staticmethod
    def show_help() -> None:
        """Displays help information."""
        help_text = """
Markdown Image Embedder

Usage: markdown_image_embedder.py [options]

Options:
  --input-file FILE, -i FILE  Use FILE as input instead of stdin
  --output-file FILE, -o FILE Write output to FILE instead of stdout
  --quality N, -q N           Set quality scale from 1-9 (default: 5)
                              Lower values = higher quality but larger files
  --yarle, -y                 Enable Yarle compatibility mode
  --max-size N, -m N          Maximum file size to embed in MB (default: 10)
                              This is the size of the base64 converted and recompressed image
  --path PATH, -p PATH        Base path for resolving relative file paths
  --debug, -d                 Enable debug logging level
  --verbose, -v               Enable verbose logging level
  --help, -h                  Display this help message

Description:
  Reads markdown from stdin (or input file if specified), downloads linked images,
  compresses them as JPEGs, and embeds them directly in the markdown as base64 data URLs.
  The modified markdown is output to stdout (or output file if specified).

Notes:
  - Files larger than max-size and video files will not be embedded
  - Requires Pillow (PIL) for image processing
  - Requires Requests for HTTP operations
"""
        print(help_text)
