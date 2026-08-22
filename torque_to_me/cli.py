"""Command-line interface for Torque to Me.

One `torque` command with a subcommand per pipeline stage:

    torque split        cut a page range out of the manual PDF
    torque check        Docling conversion preview (quality gate 1)
    torque extract      build the knowledge graph with a local LLM
    torque enrich       add derived cross-link edges to an existing graph
    torque curate-demo  apply the hand-curated demo additions (NX650 example)
    torque query        answer a maintenance question from the graph
    torque viz          render the graph to interactive HTML
    torque app          launch the Gradio demo UI (query only, no extraction)

All argument definitions live here; the implementation modules are
imported only on dispatch so that `torque split --help` never pays the
import cost of gradio or docling.
"""

import argparse
import importlib
from pathlib import Path

from torque_to_me import __version__, config


def build_parser(cfg: config.Config) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="torque",
        description="A maintenance assistant for old motorcycles, "
        "built from their scanned service manuals.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.set_defaults(cfg=cfg)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "split",
        help="Cut a page range out of the manual so the pipeline runs on one chapter",
    )
    p.add_argument("pdf", type=Path, help="Source PDF")
    p.add_argument("--pages", required=True, help="1-based inclusive page range, e.g. 20-45")
    p.add_argument("--output", type=Path, required=True, help="Output PDF path")
    p.set_defaults(runner="torque_to_me.split_pdf")

    p = sub.add_parser(
        "check",
        help="Docling conversion preview (no LLM) — judge OCR/table quality "
        "before spending GPU time",
    )
    p.add_argument("pdf", type=Path, help="PDF to convert")
    p.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/conversion_preview.md"),
        help="Where to write the markdown preview",
    )
    p.set_defaults(runner="torque_to_me.conversion_check")

    p = sub.add_parser("extract", help="Build a knowledge graph from a manual chapter")
    p.add_argument("pdf", type=Path, help="Chapter PDF")
    p.add_argument(
        "--model",
        default=cfg.extract.model,
        help="Ollama model name (default from config.toml [extract].model)",
    )
    p.add_argument(
        "--contract",
        default="dense",
        choices=["auto", "dense"],
        help="Extraction contract; 'dense' = skeleton-then-flesh, better for complex docs",
    )
    p.add_argument(
        "--tag",
        default=None,
        help="Name for this manual, e.g. 'honda-nx650'. Defaults to the PDF filename. "
        "Outputs go to outputs/<tag>/ so multiple bikes can coexist.",
    )
    p.add_argument(
        "--name",
        default=None,
        help="Bike display name shown in the app, e.g. 'Honda NX650 RD08'. Defaults to the tag.",
    )
    p.add_argument(
        "--chapter",
        default=None,
        help="Manual chapter this PDF covers, e.g. 'Lubrication'. "
        "Auto-detected from the extraction when omitted.",
    )
    p.add_argument("--outdir", type=Path, default=Path("outputs"))
    p.set_defaults(runner="torque_to_me.extract")

    p = sub.add_parser("enrich", help="Add derived cross-link edges to an extracted graph")
    p.add_argument(
        "--tag", default=None, help="Manual tag, e.g. 'demo' (reads outputs/<tag>/graph.pickle)"
    )
    p.add_argument("--graph", type=Path, default=None, help="Explicit path to a graph.pickle")
    p.set_defaults(runner="torque_to_me.graph_enrich")

    p = sub.add_parser(
        "curate-demo",
        help="Apply the hand-curated additions to the demo graph "
        "(Honda NX650 Lubrication chapter — a worked example of the "
        "human-in-the-loop pass)",
    )
    p.add_argument("--tag", default="demo", help="Manual tag (outputs/<tag>/graph.pickle)")
    p.set_defaults(runner="torque_to_me.curate_demo")

    p = sub.add_parser("query", help="Answer a maintenance question from the knowledge graph")
    p.add_argument("question", help="Maintenance question")
    p.add_argument(
        "--model",
        default=cfg.answer.model,
        help="Ollama model (default from config.toml [answer].model)",
    )
    p.add_argument(
        "--tag",
        default=None,
        help="Manual tag used at extraction (outputs/<tag>/graph.pickle). "
        "If omitted and exactly one graph exists, it is used.",
    )
    p.add_argument("--graph", type=Path, default=None, help="Explicit graph path (overrides --tag)")
    p.add_argument("--top", type=int, default=cfg.answer.top_nodes, help="Seed nodes to retrieve")
    p.add_argument("--show-facts", action="store_true", help="Print retrieved facts")
    p.set_defaults(runner="torque_to_me.query")

    p = sub.add_parser("viz", help="Render the knowledge graph to an interactive HTML page")
    p.add_argument("--graph", type=Path, default=None, help="Explicit graph path")
    p.add_argument("--tag", default=None, help="Manual tag (outputs/<tag>/graph.pickle)")
    p.add_argument("--output", type=Path, default=None)
    p.set_defaults(runner="torque_to_me.visualize")

    p = sub.add_parser(
        "app",
        help="Launch the Torque to Me demo UI (query and visualize existing graphs)",
    )
    p.add_argument(
        "--answer-model",
        default=cfg.answer.model,
        help="Fast Ollama model for answering questions (default from config.toml [answer].model)",
    )
    p.add_argument("--port", type=int, default=7860)
    p.set_defaults(runner="torque_to_me.app")

    return parser


def main(argv: list[str] | None = None) -> None:
    cfg = config.load()
    parser = build_parser(cfg)
    args = parser.parse_args(argv)
    module = importlib.import_module(args.runner)
    module.run(args)


if __name__ == "__main__":
    main()
