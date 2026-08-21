#!/usr/bin/env python3
"""
Cut a page range out of the manual so the pipeline runs on one chapter.

Usage:
    python scripts/01_split_pdf.py data/input/manual.pdf \
        --pages 20-45 --output data/input/chapter_maintenance.pdf
"""

import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a page range out of a PDF")
    parser.add_argument("pdf", type=Path, help="Source PDF")
    parser.add_argument(
        "--pages",
        required=True,
        help="1-based inclusive page range, e.g. 20-45",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output PDF path")
    args = parser.parse_args()

    start_s, _, end_s = args.pages.partition("-")
    start, end = int(start_s), int(end_s or start_s)

    reader = PdfReader(args.pdf)
    total = len(reader.pages)
    if not (1 <= start <= end <= total):
        raise SystemExit(f"Range {start}-{end} outside document (has {total} pages)")

    writer = PdfWriter()
    for i in range(start - 1, end):
        writer.add_page(reader.pages[i])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "wb") as f:
        writer.write(f)

    print(f"Wrote pages {start}-{end} ({end - start + 1} pages) -> {args.output}")


if __name__ == "__main__":
    main()
