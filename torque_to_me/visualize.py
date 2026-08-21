"""
Render the knowledge graph to an interactive HTML page with pyvis.
Open the HTML, arrange the physics until it looks good, screenshot or
screen-record.

(docling-graph's own `docling-graph inspect outputs` gives a richer
Cytoscape view if you ran the CLI convert path; this command works from
the pickled graph produced by `torque extract`.)

Usage:
    torque viz
    # then open outputs/<tag>/graph.html in a browser
"""

import argparse
import pickle

import networkx as nx

from torque_to_me import bike_meta
from torque_to_me.graph_viz import build_network, html_doc


def run(args: argparse.Namespace) -> None:
    args.graph = bike_meta.resolve_graph_path(args.tag, args.graph)

    if args.output is None:
        args.output = args.graph.parent / "graph.html"

    with open(args.graph, "rb") as f:
        graph: nx.DiGraph = pickle.load(f)

    net = build_network(graph)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_doc(net))
    print(f"Wrote {args.output} ({graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges)")
    print("Open it in a browser, let the layout settle, then screenshot.")
