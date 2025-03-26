"""
Setup script for MarkdownImageEmbedder.
"""

from setuptools import setup, find_packages
import os

# Read the contents of README.md
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read version from __init__.py
with open(os.path.join(this_directory, '__init__.py'), encoding='utf-8') as f:
    for line in f:
        if line.startswith('__version__'):
            version = line.split('=')[1].strip().strip('"\'')
            break

setup(
    name="markdown-image-embedder",
    version=version,
    description="Embeds images in markdown files as base64 encoded data URLs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="",
    author_email="",
    url="",
    # Include all package files
    packages=find_packages() or ['.'],
    # Make sure to include top-level Python files as well
    py_modules=["base64_encoder", "cli_parser", "http_client", "image_processor", 
                "logger_setup", "markdown_processor", "__main__", "markdownimageembedder"],
    # Create entry point using the main function
    entry_points={
        "console_scripts": [
            "markdown-image-embedder=__main__:main",
        ],
    },
    install_requires=[
        "pillow>=8.0.0",
        "requests>=2.25.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Text Processing :: Markup :: Markdown",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
)
