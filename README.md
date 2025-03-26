# Markdown Image Embedder

A utility that embeds external images in Markdown files as base64-encoded data URLs, creating completely self-contained documents.

## Features

- Converts both local and remote images in Markdown to base64-encoded data URLs
- Automatically compresses images to reduce file size
- Intelligent quality adjustment based on image size
- Supports both standard Markdown image syntax `![alt](url)` and Obsidian-style `![[image.jpg]]`
- Makes remote images clickable, linking to their original URLs
- Configurable compression quality
- Supports various image formats (JPG, PNG, GIF, etc.)
- Preserves image dimensions when specified
- Skips already embedded images and video files

## Installation

### Requirements

- Python 3.6+
- Required Python packages:
  - Pillow (PIL)
  - requests

### Install from source

```bash
# Clone the repository
git clone https://github.com/yourusername/markdown-image-embedder.git
cd markdown-image-embedder

# Install dependencies
pip install pillow requests
```

## Usage

### Basic Usage

```bash
# Process a Markdown file
python markdown_image_embedder.py -i input.md -o output.md

# Pipe content through stdin/stdout
cat input.md | python markdown_image_embedder.py > output.md
```

### Examples

**Embed images with default settings:**
```bash
python markdown_image_embedder.py -i notes.md -o notes_embedded.md
```

**Specify a base path for relative image links:**
```bash
python markdown_image_embedder.py -i notes.md -o notes_embedded.md -p /path/to/images
```

**Set higher image quality (lower value = higher quality):**
```bash
python markdown_image_embedder.py -i notes.md -o notes_embedded.md -q 2
```

**Enable Obsidian/Yarle compatibility mode:**
```bash
python markdown_image_embedder.py -i notes.md -o notes_embedded.md -y
```

### Command Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--input-file` | `-i` | stdin | Input Markdown file path |
| `--output-file` | `-o` | stdout | Output Markdown file path |
| `--quality` | `-q` | 5 | Quality scale (1-9, lower = higher quality) |
| `--yarle` | `-y` | False | Enable Yarle compatibility mode |
| `--max-size` | `-m` | 10 | Maximum file size to embed in MB |
| `--path` | `-p` | "" | Base path for resolving relative file paths |
| `--debug` | `-d` | False | Enable debug logging level |
| `--verbose` | `-v` | False | Enable verbose logging level |

## Why use Markdown Image Embedder?

- **Create self-contained documents** that don't rely on external resources
- **Prevent broken image links** when sharing Markdown files
- **Simplify document sharing** without separate image folders
- **Optimize file size** with automatic compression
- **Preserve offline access** to all content

## License

[MIT License](LICENSE)
