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
from pyvis.network import Network

COLORS = {
    "Procedure": "#e63946",
    "TorqueSpec": "#457b9d",
    "Part": "#2a9d8f",
    "Symptom": "#e9c46a",
}
DEFAULT_COLOR = "#8d99ae"


def node_type(data: dict) -> str:
    for key in ("__label__", "label", "type", "node_type"):
        v = data.get(key)
        if isinstance(v, str) and v:
            return v
    return "Node"


def node_caption(data: dict) -> str:
    for key in ("title", "fastener", "name", "description", "chapter_title"):
        v = data.get(key)
        if isinstance(v, str) and v:
            return v[:60]
    return "?"


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

    net = Network(
        height="900px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#1d3557",
        cdn_resources="in_line",
    )
    net.barnes_hut(gravity=-3000, central_gravity=0.2, spring_length=140)

    for node_id, data in graph.nodes(data=True):
        ntype = node_type(data)
        prov = data.get("__provenance__", "")
        hover = "\n".join(
            f"{k}: {v}" for k, v in data.items()
            if not k.startswith("__") and v not in (None, [], "")
        )
        if prov:
            hover += f"\n\nprovenance: {prov}"
        net.add_node(
            str(node_id),
            label=node_caption(data),
            title=hover or str(node_id),
            color=COLORS.get(ntype, DEFAULT_COLOR),
            shape="dot",
            size=18 if ntype == "Procedure" else 12,
        )

    for u, v, edata in graph.edges(data=True):
        label = edata.get("label", edata.get("type", ""))
        net.add_edge(str(u), str(v), label=label, arrows="to", font={"size": 9})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(args.output))
    print(f"Wrote {args.output} ({graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges)")
    print("Open it in a browser, let the layout settle, then screenshot.")


if __name__ == "__main__":
    main()
