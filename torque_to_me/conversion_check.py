"""
Quality gate 1: run Docling conversion only (no LLM) and dump the result
as markdown so you can judge OCR/table quality before spending GPU time
on extraction.

Usage:
    torque check data/input/chapter_maintenance.pdf
"""

import argparse
import sys

from docling.document_converter import DocumentConverter


def run(args: argparse.Namespace) -> None:
    if not args.pdf.exists():
        sys.exit(f"File not found: {args.pdf}")

    print(f"Converting {args.pdf} (first run downloads Docling models)...")
    converter = DocumentConverter()
    result = converter.convert(str(args.pdf))
    markdown = result.document.export_to_markdown()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")

    n_tables = markdown.count("|---")
    print(f"\nWrote {args.output} ({len(markdown):,} chars, ~{n_tables} tables detected)")
    print("\nGATE: open the file and check:")
    print("  1. Torque tables survived as tables (rows/columns intact)")
    print("  2. Numbers are correct (compare 3-4 values against the paper manual)")
    print("  3. Section headings are recognized")
    print("If tables are mangled, do NOT proceed: get a better scan or try the VLM path.")
