"""
Cut a page range out of the manual so the pipeline runs on one chapter.

Usage:
    torque split data/input/manual.pdf \
        --pages 20-45 --output data/input/chapter_maintenance.pdf
"""

import argparse

from pypdf import PdfReader, PdfWriter


def run(args: argparse.Namespace) -> None:
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
