#!/usr/bin/env python3
"""
Example script demonstrating how to use MarkdownImageEmbedder programmatically.
"""

import sys
import logging
from markdownimageembedder_py.http_client import create_http_client
from markdownimageembedder_py.image_processor import ImageProcessor
from markdownimageembedder_py.markdown_processor import MarkdownProcessor


def main():
    """
    Example of how to use MarkdownImageEmbedder programmatically.
    """
    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s', stream=sys.stderr)
    
    # Sample markdown with an image
    markdown = """# Sample Document
    
This is a test document with an image:

![Example Image](https://example.com/image.jpg)

And some more text after the image.
"""
    
    # Create required components
    http_client = create_http_client()
    image_processor = ImageProcessor(quality_scale=5)  # Default quality
    
    # Create markdown processor
    markdown_processor = MarkdownProcessor(
        http_client=http_client,
        image_processor=image_processor,
        yarle_mode=False,
        max_file_size_bytes=10 * 1024 * 1024,  # 10 MB
        base_path=""
    )
    
    # Process the markdown
    try:
        processed_markdown = markdown_processor.process(markdown)
        
        # Print the processed markdown to stdout
        print(processed_markdown)
        
        # Report statistics to stderr
        print(f"\nImages processed: {markdown_processor.images_processed}", file=sys.stderr)
        print(f"Total original size: {markdown_processor.total_image_size} bytes", file=sys.stderr)
        print(f"Total compressed size: {markdown_processor.total_compressed_size} bytes", file=sys.stderr)
        
        # Report any non-embedded resources
        if markdown_processor.non_embedded_resources:
            print("\nThe following resources were not embedded:", file=sys.stderr)
            for resource in markdown_processor.non_embedded_resources:
                print(f"  - {resource}", file=sys.stderr)
                
    except Exception as e:
        print(f"Error processing markdown: {e}", file=sys.stderr)
        return 1
        
    return 0


if __name__ == "__main__":
    sys.exit(main())
