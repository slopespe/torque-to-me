"""Shared pyvis rendering for knowledge (sub)graphs.

Used by app.py (per-question retrieved-subgraph panel) and
visualize.py (whole-graph HTML export).
"""

import html

import networkx as nx
from pyvis.network import Network

COLORS = {
    "Procedure": "#e63946",
    "TorqueSpec": "#457b9d",
    "Part": "#2a9d8f",
    "Symptom": "#e9c46a",
    "MaintenanceItem": "#8367c7",
}
DEFAULT_COLOR = "#8d99ae"


def node_type(data: dict) -> str:
    for key in ("__label__", "label", "type", "node_type"):
        v = data.get(key)
        if isinstance(v, str) and v and v != "entity":
            return v
    return "Node"


def node_caption(data: dict) -> str:
    for key in ("title", "fastener", "name", "item", "description", "chapter_title"):
        v = data.get(key)
        if isinstance(v, str) and v:
            return v[:60]
    return "?"


def _hover_value(value, limit: int = 220) -> str:
    if isinstance(value, list):
        value = " | ".join(str(v) for v in value)
    value = str(value)
    return value[: limit - 1] + "…" if len(value) > limit else value


def _hover(data: dict) -> str:
    lines = [
        f"{k}: {_hover_value(v)}"
        for k, v in data.items()
        if not k.startswith("__") and v not in (None, [], "")
    ]
    prov = data.get("__provenance__")
    if isinstance(prov, dict):
        bits = []
        pages = prov.get("pages")
        if pages:
            word = "page" if len(pages) == 1 else "pages"
            bits.append(f"{word} " + ", ".join(str(p) for p in pages))
        if prov.get("manual_section"):
            bits.append(str(prov["manual_section"]))
        if bits:
            lines.append("source: " + "; ".join(bits))
    elif prov:
        lines.append(f"source: {_hover_value(prov)}")
    return "\n".join(lines)


# vis-network's default tooltip is white-space:nowrap, so multi-line node
# details overflow the canvas and get cut off. Wrap and cap it instead.
_TOOLTIP_CSS = """
<style>
  div.vis-tooltip {
    white-space: pre-wrap !important;
    overflow-wrap: break-word;
    max-width: 340px;
    max-height: 360px;
    overflow-y: hidden;
    font-size: 12px !important;
    line-height: 1.35;
  }
</style>
"""


def html_doc(net: Network) -> str:
    """The pyvis page with the tooltip fix applied."""
    return net.generate_html().replace("</head>", _TOOLTIP_CSS + "</head>", 1)


def build_network(
    graph: nx.DiGraph,
    nodes=None,
    seeds=frozenset(),
    height: str = "900px",
) -> Network:
    """Render `nodes` of `graph` (default: all) as a pyvis network.

    Seed nodes (the retrieval hits) are drawn larger with a dark border.
    """
    net = Network(
        height=height,
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#1d3557",
        cdn_resources="in_line",  # self-contained: works offline
    )
    net.barnes_hut(gravity=-3000, central_gravity=0.2, spring_length=140)

    shown = set(graph.nodes if nodes is None else nodes)
    for node_id in shown:
        data = graph.nodes[node_id]
        ntype = node_type(data)
        color = COLORS.get(ntype, DEFAULT_COLOR)
        seed = node_id in seeds
        net.add_node(
            str(node_id),
            label=node_caption(data),
            title=_hover(data) or str(node_id),
            color={"background": color, "border": "#1d3557" if seed else color},
            borderWidth=3 if seed else 1,
            shape="dot",
            size=(22 if seed else 18) if ntype == "Procedure" else (16 if seed else 12),
        )
    for u, v, edata in graph.edges(data=True):
        if u in shown and v in shown:
            label = edata.get("label", edata.get("type", ""))
            net.add_edge(str(u), str(v), label=label, arrows="to", font={"size": 9})
    return net


def subgraph_iframe(graph: nx.DiGraph, nodes, seeds=frozenset(), height: int = 460) -> str:
    """Self-contained <iframe> showing the retrieved subgraph.

    pyvis produces a full HTML document; srcdoc keeps its scripts and
    styles isolated from the Gradio page.
    """
    doc = html_doc(build_network(graph, nodes=nodes, seeds=seeds, height=f"{height - 20}px"))
    return (
        f'<iframe style="width:100%;height:{height}px;border:1px solid #ddd;'
        f'border-radius:8px;background:#fff" srcdoc="{html.escape(doc, quote=True)}"></iframe>'
    )


def legend_html(note: str = "") -> str:
    dots = "".join(
        f'<span style="margin-right:14px;white-space:nowrap">'
        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f'background:{color};vertical-align:baseline"></span> {label}</span>'
        for label, color in COLORS.items()
    )
    if note:
        note = f'<span style="opacity:0.7">{note}</span>'
    return f'<div style="font-size:0.85em;margin:4px 2px">{dots}{note}</div>'
