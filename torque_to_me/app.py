"""
Torque to Me — a maintenance assistant for old motorcycles.

Pick a bike and ask maintenance questions. Answers are grounded in the
bike's knowledge graph; the right panel shows the exact facts and manual
pages used.

The app is read-only: it queries and visualizes graphs that already
exist. Building a graph from a manual is a CLI job (`torque split`,
`torque check`, `torque extract`) — it takes minutes to tens of minutes
and wants the quality gates a terminal gives you.

Graphs are read per bike from outputs/<tag>/graph.pickle, so several
motorcycles can live side by side.

Usage:
    torque extract data/input/chapter.pdf --tag my-bike --name "My Bike"
    torque app
    # then open http://localhost:7860

The answering model and its settings come from config.toml (see
torque_to_me/config.py for the defaults); --answer-model overrides it.
"""

import argparse
import base64
import functools
import pickle
from pathlib import Path

import gradio as gr
import networkx as nx

from torque_to_me import bike_meta, config, graph_viz
from torque_to_me import query as q

OUTPUTS = Path("outputs")
ICON = Path(__file__).resolve().parent / "assets" / "icon.png"

EXAMPLES = [
    "What oil does the engine take and how much?",
    "What is the torque for the oil drain plug?",
    "How do I check the engine oil level?",
    "How do I clean the oil strainer screen?",
    "The oil level keeps dropping, what could be the cause?",
]

NO_BIKES = (
    "No bike graphs in `outputs/` yet. Build one from the command line:\n\n"
    "```bash\n"
    "torque split data/input/manual.pdf --pages 20-45 \\\n"
    "    --output data/input/chapter.pdf\n"
    'torque extract data/input/chapter.pdf --tag my-bike --name "My Bike"\n'
    "```\n\n"
    "Then click **Refresh list**."
)


# ----------------------------------------------------------------------
# Graph registry
# ----------------------------------------------------------------------


def list_bikes() -> list[tuple[str, str]]:
    """(label, tag) dropdown choices: 'Honda NX650 RD08 — Lubrication'."""
    return sorted(
        ((bike_meta.label(p.parent), p.parent.name) for p in OUTPUTS.glob("*/graph.pickle")),
        key=lambda pair: pair[0].lower(),
    )


def load_graph(tag: str) -> nx.DiGraph:
    with open(OUTPUTS / tag / "graph.pickle", "rb") as f:
        return pickle.load(f)


# ----------------------------------------------------------------------
# Question answering
# ----------------------------------------------------------------------


def answer(tag: str, question: str, model: str, cfg: config.Config):
    """Retrieve facts, then stream the model's answer.

    A generator so the provenance panel (subgraph plot + text facts) fills
    in immediately — retrieval is milliseconds — while the model works.
    """
    question = (question or "").strip()
    if not tag:
        yield "Pick a bike first (build one with `torque extract`).", "", ""
        return
    if not question:
        yield "Ask a maintenance question.", "", ""
        return

    graph = load_graph(tag)
    ranked = q.score_nodes(graph, question)
    if not ranked:
        yield "Nothing in this manual's graph matches that question.", "", ""
        return

    seeds = [node_id for node_id, _ in ranked[: cfg.answer.top_nodes]]
    nodes = q.collect_subgraph(graph, seeds)
    facts = q.format_facts(graph, nodes)
    subgraph = graph_viz.subgraph_iframe(graph, nodes, seeds=set(seeds))
    bike = bike_meta.display_name(OUTPUTS / tag)
    prompt = q.PROMPT_TEMPLATE.format(facts=facts, question=question, bike=bike)

    yield "*Reading the manual...*", subgraph, facts
    reply_parts = []
    thinking_shown = False
    try:
        for kind, chunk in q.stream_ollama(model, prompt, cfg):
            if kind == "thinking":
                if not thinking_shown:
                    thinking_shown = True
                    yield (
                        "*Thinking... (a thinking model can take a few minutes)*",
                        gr.skip(),
                        gr.skip(),
                    )
                continue
            reply_parts.append(chunk)
            yield "".join(reply_parts), gr.skip(), gr.skip()
    except Exception as e:  # noqa: BLE001
        yield f"Ollama call failed: {e}\nIs `ollama serve` running?", gr.skip(), gr.skip()


# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------


def build_app(answer_model: str, cfg: config.Config) -> gr.Blocks:
    tagline = (
        "A maintenance assistant for old motorcycles, built from their "
        "scanned service manuals. Pick a bike and ask. Every answer is "
        "grounded: you see the exact facts and manual pages it came "
        "from. Runs fully local, your manual never leaves this machine."
    )
    with gr.Blocks(title="Torque to Me") as app:
        if ICON.exists():
            # Base64 so the header needs no static-file route.
            icon_b64 = base64.b64encode(ICON.read_bytes()).decode()
            gr.HTML(
                '<div style="display:flex;align-items:center;gap:16px;margin:8px 0;">'
                f'<img src="data:image/png;base64,{icon_b64}" alt="Torque to Me" '
                'style="width:72px;height:72px;border-radius:14px;flex-shrink:0;">'
                '<div><h1 style="margin:0;">Torque to Me</h1>'
                f'<p style="margin:6px 0 0;">{tagline}</p></div></div>'
            )
        else:
            gr.Markdown("# Torque to Me\n" + tagline)

        bikes = list_bikes()
        with gr.Row():
            bike_dd = gr.Dropdown(
                choices=bikes,
                value=(bikes[0][1] if bikes else None),
                label="Bike",
                scale=3,
            )
            refresh_btn = gr.Button("Refresh list", scale=1)
        # Only shown while outputs/ has no graph: the app cannot build one.
        empty_note = gr.Markdown(NO_BIKES, visible=not bikes)
        with gr.Row():
            with gr.Column(scale=3):
                question = gr.Textbox(
                    label="Question",
                    placeholder="e.g. What is the torque for the rear axle nut?",
                )
                ask_btn = gr.Button("Ask", variant="primary")
                gr.Examples(examples=EXAMPLES, inputs=question)
                answer_box = gr.Markdown(label="Answer")
            with gr.Column(scale=2):
                gr.Markdown(
                    "**Retrieved subgraph (provenance)** — the nodes and "
                    "relations the answer is grounded in; retrieval hits "
                    "have a dark border, neighbors were pulled in with "
                    "them. Drag to rearrange, hover for details."
                )
                gr.HTML(graph_viz.legend_html())
                subgraph_box = gr.HTML()
                with gr.Accordion("Facts as text (exactly what the model sees)", open=False):
                    facts_box = gr.Textbox(
                        show_label=False,
                        lines=14,
                        interactive=False,
                    )

        def refresh():
            found = list_bikes()
            return gr.update(choices=found), gr.update(visible=not found)

        refresh_btn.click(refresh, outputs=[bike_dd, empty_note])
        # functools.partial, not a lambda: Gradio only streams the
        # generator's yields if it can see a generator function.
        gr.on(
            [ask_btn.click, question.submit],
            functools.partial(answer, model=answer_model, cfg=cfg),
            inputs=[bike_dd, question],
            outputs=[answer_box, subgraph_box, facts_box],
        )

    return app


def run(args: argparse.Namespace) -> None:
    OUTPUTS.mkdir(exist_ok=True)
    bikes = list_bikes()
    print(
        f"Found {len(bikes)} bike graph(s): {', '.join(label for label, _ in bikes) or 'none yet'}"
    )
    if not bikes:
        print("Build one with `torque extract` — the app only queries existing graphs.")
    print(f"Answering with {args.answer_model}")
    build_app(args.answer_model, args.cfg).launch(
        server_port=args.port,
        favicon_path=str(ICON) if ICON.exists() else None,
    )
