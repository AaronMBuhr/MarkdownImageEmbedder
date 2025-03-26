"""
Main entry point for MarkdownImageEmbedder.
"""

import sys
import logging
from typing import List, Optional

# Use direct imports instead of relative ones
from cli_parser import CommandLineParser
from http_client import create_http_client
from image_processor import ImageProcessor
from logger_setup import LoggerSetup
from markdown_processor import MarkdownProcessor


def main(args: Optional[List[str]] = None) -> int:
    """
    Main entry point for the application.
    
    Args:
        args: Command line arguments (uses sys.argv[1:] if None)
        
    Returns:
        int: Exit code
    """
    if args is None:
        args = sys.argv[1:]
        
    # Parse command line options
    options = CommandLineParser.parse(args)
    
    # Show help if requested
    if "--help" in args or "-h" in args:
        CommandLineParser.show_help()
        return 0
    
    # Initialize logger
    LoggerSetup.initialize_logger(options.debug, options.verbose)
    logger = LoggerSetup.get_logger()
    
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
            
        # Create HTTP client
        http_client = create_http_client()
        
        # Create image processor
        image_processor = ImageProcessor(options.quality_scale)
        
        # Create markdown processor
        markdown_processor = MarkdownProcessor(
            http_client,
            image_processor,
            options.yarle_mode,
            options.max_file_size_mb * 1024 * 1024,  # Convert MB to bytes
            options.base_path
        )
        
        # Process markdown
        logger.info("Processing markdown...")
        output_markdown = markdown_processor.process(input_markdown)
        
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
            
        # Log non-embedded resources
        if markdown_processor.non_embedded_resources:
            logger.info("\nThe following resources were not embedded and need to be preserved:")
            for resource in markdown_processor.non_embedded_resources:
                logger.info(f"  {resource}")
                
        return 0
        
    except Exception as e:
        logger.error(f"Error: {e}")
        if options.debug:
            logger.exception("Stack trace:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
