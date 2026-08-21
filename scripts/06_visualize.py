#!/usr/bin/env python3
"""
Render the knowledge graph to an interactive HTML page with pyvis.
This is the scroll-stopping visual for the LinkedIn post: open the HTML,
arrange the physics until it looks good, screenshot or screen-record.

(docling-graph's own `docling-graph inspect outputs` gives a richer
Cytoscape view if you ran the CLI convert path; this script works from
the pickled graph produced by 03_extract.py.)

Usage:
    python scripts/06_visualize.py
    # then open outputs/graph.html in a browser
"""

import argparse
import pickle
import sys
from pathlib import Path

import networkx as nx

from graph_viz import build_network, html_doc


def main() -> None:
    parser = argparse.ArgumentParser(description="Render graph to interactive HTML")
    parser.add_argument("--graph", type=Path, default=None, help="Explicit graph path")
    parser.add_argument("--tag", default=None, help="Manual tag (outputs/<tag>/graph.pickle)")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if args.graph is None:
        candidates = sorted(Path("outputs").glob("*/graph.pickle"))
        if args.tag:
            args.graph = Path("outputs") / args.tag / "graph.pickle"
        elif len(candidates) == 1:
            args.graph = candidates[0]
        elif not candidates:
            sys.exit("No graphs found under outputs/. Run scripts/03_extract.py first.")
        else:
            tags = ", ".join(c.parent.name for c in candidates)
            sys.exit(f"Multiple graphs found ({tags}). Pick one with --tag.")

    if not args.graph.exists():
        sys.exit(f"Graph not found at {args.graph}. Run scripts/03_extract.py first.")

    if args.output is None:
        args.output = args.graph.parent / "graph.html"

    with open(args.graph, "rb") as f:
        graph: nx.DiGraph = pickle.load(f)

    net = build_network(graph)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_doc(net))
    print(f"Wrote {args.output} ({graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges)")
    print("Open it in a browser, let the layout settle, then screenshot.")


if __name__ == "__main__":
    main()
