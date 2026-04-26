"""Convert a PDF page to SVG using PyMuPDF — preserves vector text and geometry.

Usage:
    "C:/Program Files/FreeCAD 1.1/bin/python.exe" scripts/pdf_to_svg.py \
        images/fridge-cup-pdf.pdf images/fridge-cup-dimensions.svg

Optional:
    --page N    1-based page index to extract (default: 1)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf


def convert(src: Path, dst: Path, page_index: int) -> None:
    doc = pymupdf.open(src)
    if page_index < 1 or page_index > doc.page_count:
        sys.exit(f"PDF has {doc.page_count} page(s); requested page {page_index}.")
    page = doc[page_index - 1]
    svg = page.get_svg_image(text_as_path=False)
    dst.write_text(svg, encoding="utf-8")
    doc.close()
    print(f"Wrote {dst} ({len(svg):,} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("src", type=Path, help="Input .pdf file")
    parser.add_argument("dst", type=Path, help="Output .svg file")
    parser.add_argument("--page", type=int, default=1, help="1-based page index (default: 1)")
    args = parser.parse_args()

    if not args.src.exists():
        sys.exit(f"Input file not found: {args.src}")
    args.dst.parent.mkdir(parents=True, exist_ok=True)

    convert(args.src, args.dst, args.page)


if __name__ == "__main__":
    main()
