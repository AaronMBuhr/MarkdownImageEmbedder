#!/usr/bin/env python3
"""
move_data_images.py

Turn inline Markdown images with data: URIs into reference-style images
and move all data: URIs to the bottom of the file.

Example:

    ![](data:image/jpeg;base64,AAA...)

becomes something like:

    ![][dataimg-image-1]

and at the bottom of the file you'll get:

    <!-- Image references (auto-generated from inline data URIs) -->
    [dataimg-image-1]: data:image/jpeg;base64,AAA...

Usage:
    python move_data_images.py input.md output.md
"""

import argparse
import glob
import os
import re
import shutil
import sys
from collections import OrderedDict


IMAGE_RE = re.compile(
    r'!\[(?P<alt>[^\]]*)\]\((?P<src>data:image[^)]*)\)',
    re.IGNORECASE,
)


def make_id(alt_text: str, existing_ids: set) -> str:
    """Build a reasonably readable, unique id like dataimg-some-alt-text."""
    base = (alt_text or "").strip().lower()
    base = re.sub(r'[^a-z0-9]+', '-', base).strip('-') or "image"
    candidate = f"dataimg-{base}"
    i = 2
    while candidate in existing_ids:
        candidate = f"dataimg-{base}-{i}"
        i += 1
    return candidate


def transform(markdown: str) -> str:
    """
    Replace inline data:image Markdown with reference-style images
    and return the new Markdown with a reference block appended.
    """
    # src -> (id, alt)
    refs: "OrderedDict[str, tuple[str,str]]" = OrderedDict()
    existing_ids: set[str] = set()

    def replacer(match: re.Match) -> str:
        alt = match.group("alt") or ""
        src = match.group("src")

        if src in refs:
            img_id, _ = refs[src]
        else:
            img_id = make_id(alt, existing_ids)
            refs[src] = (img_id, alt)
            existing_ids.add(img_id)

        # keep the original alt text
        return f"![{alt}][{img_id}]"

    new_body = IMAGE_RE.sub(replacer, markdown)

    if not refs:
        # nothing to do
        return markdown

    # Avoid duplicating our own block if script is re-run
    marker = "<!-- Image references (auto-generated from inline data URIs) -->"
    if marker in new_body:
        new_body = new_body.split(marker, 1)[0].rstrip()

    lines = [new_body.rstrip(), "", marker]
    for src, (img_id, _alt) in refs.items():
        lines.append(f"[{img_id}]: {src}")
    lines.append("")  # final newline

    return "\n".join(lines)


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert inline data:image Markdown to reference-style images\n"
            "and move all data: URIs to the bottom of the file."
        )
    )
    parser.add_argument(
        "input",
        nargs="+",
        help="Input markdown file(s) or glob pattern(s) (e.g. *.md)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        help="Output markdown file (omit when using --overwrite)",
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        help="Overwrite the original input file in place.",
    )
    parser.add_argument(
        "-b",
        "--backup",
        action="store_true",
        help="Create a .bak backup of the original file before overwriting (requires --overwrite).",
    )

    args = parser.parse_args(argv[1:])

    if args.backup and not args.overwrite:
        parser.error("--backup/ -b can only be used together with --overwrite/ -o.")

    # Expand input patterns
    all_files: list[str] = []
    for pattern in args.input:
        # If the pattern is a real file, keep it; otherwise treat as glob
        if os.path.isfile(pattern):
            all_files.append(pattern)
        else:
            expanded = glob.glob(pattern)
            all_files.extend(expanded)

    # De-duplicate while preserving order
    seen: set[str] = set()
    unique_files: list[str] = []
    for path in all_files:
        if path not in seen:
            seen.add(path)
            unique_files.append(path)

    if not unique_files:
        print("ERROR: No input files matched.", file=sys.stderr)
        raise SystemExit(1)

    # Overwrite mode: process each input file in place (optionally with backups)
    if args.overwrite:
        if args.output:
            parser.error("Do not specify an output file when using --overwrite/ -o.")

        for input_path in unique_files:
            # If requested, back up the original before we overwrite
            if args.backup:
                backup_path = input_path + ".bak"
                try:
                    shutil.copy2(input_path, backup_path)
                except Exception as e:
                    print(
                        f"ERROR: Failed to create backup '{backup_path}': {e}",
                        file=sys.stderr,
                    )
                    raise SystemExit(1)

            with open(input_path, "r", encoding="utf-8") as f:
                text = f.read()

            transformed = transform(text)

            with open(input_path, "w", encoding="utf-8") as f:
                f.write(transformed)

    else:
        # Non-overwrite mode: must be exactly one resolved input file + explicit output
        if not args.output:
            parser.error("You must provide an output file when not using --overwrite/ -o.")
        if len(unique_files) != 1:
            parser.error(
                "When not using --overwrite/ -o, exactly one input file (after globbing) must match."
            )

        input_path = unique_files[0]
        output_path = args.output

        with open(input_path, "r", encoding="utf-8") as f:
            text = f.read()

        transformed = transform(text)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(transformed)


if __name__ == "__main__":
    main(sys.argv)
