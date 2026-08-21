"""
Torque to Me — a maintenance assistant for old motorcycles.

Two tabs:
  1. "Your manual": upload a scanned service manual PDF (ideally one
     chapter, not the whole book), give the bike a name, and build its
     knowledge graph. Extraction is the slow step: minutes to tens of
     minutes on local hardware. Progress streams into the status box.
  2. "Torque to me": pick a bike and ask maintenance questions. Answers
     are grounded in the graph; the right panel shows the exact facts
     and manual pages used.

Graphs are stored per bike under outputs/<tag>/graph.pickle, so several
motorcycles can live side by side.

Usage:
    torque app
    # then open http://localhost:7860

Models and their settings come from config.toml (see
torque_to_me/config.py for the defaults); --answer-model /
--extract-model override it. Two models: a fast one answers questions in
seconds; the slower thinking model is only used when building a graph
from a manual.
"""

import argparse
import functools
import pickle
import re
import shutil
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


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "my-bike"


# ----------------------------------------------------------------------
# Ingestion (upload -> knowledge graph)
# ----------------------------------------------------------------------


def ingest(pdf_file, bike_name: str, chapter: str, model: str, cfg: config.Config):
    """Run the docling-graph pipeline on an uploaded manual."""
    if pdf_file is None:
        yield "Upload a PDF first."
        return
    if not bike_name or not bike_name.strip():
        yield "Give the bike a name first (e.g. 'Honda NX650 RD08')."
        return
    bike_name = bike_name.strip()

    tag = slugify(bike_name)
    outdir = OUTPUTS / tag
    outdir.mkdir(parents=True, exist_ok=True)

    src = Path(pdf_file)
    dest = outdir / "manual.pdf"
    shutil.copy(src, dest)

    yield (
        f"Manual saved for '{bike_name}' (tag: {tag}).\n"
        f"Building the knowledge graph with ollama/{model}...\n"
        "This is the slow step: minutes to tens of minutes depending on "
        "hardware and chapter size. Leave this tab open."
    )

    try:
        # Imported lazily so the app starts fast; extraction dependencies
        # only load when a manual is actually uploaded.
        from docling_graph import run_pipeline

        from torque_to_me.templates.service_manual import ServiceManualChapter

        pipeline_config = {
            "source": str(dest),
            "template": ServiceManualChapter,
            "backend": "llm",
            "inference": "local",
            "processing_mode": "many-to-one",
            "extraction_contract": "dense",
            # ollama_chat: the legacy ollama/ route returns empty content
            # for thinking models (see extract.py).
            "provider_override": "ollama_chat",
            "model_override": model,
            "structured_output": True,
            "use_chunking": True,
            # Single worker + long timeout: Ollama serves one request at a
            # time (see extract.py).
            "parallel_workers": cfg.extract.parallel_workers,
            "llm_overrides": {
                "max_output_tokens": cfg.extract.max_output_tokens,
                "reliability": {"timeout_s": cfg.extract.timeout_s},
            },
        }
        context = run_pipeline(pipeline_config)
        graph = context.knowledge_graph

        # Recover cross-links the LLM left as prose (see graph_enrich.py).
        from torque_to_me.graph_enrich import enrich

        enrich(graph)

        with open(outdir / "graph.pickle", "wb") as f:
            pickle.dump(graph, f)

        # Chapter typed by the user, else the title the extraction found.
        bike_meta.write(
            outdir,
            name=bike_name,
            chapter=(chapter or "").strip() or bike_meta.chapter_from_graph(graph),
        )

        yield (
            f"Done. Knowledge graph for '{bike_name}': "
            f"{graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges.\n"
            f"Saved to {outdir / 'graph.pickle'}.\n\n"
            "Go to the 'Torque to me' tab, refresh the bike list, and ask away.\n"
            "Tip: spot-check a few torque values against the paper manual "
            "before trusting it on your actual bike."
        )
    except Exception as e:  # noqa: BLE001
        yield (
            f"Extraction failed: {e}\n\n"
            "Common causes: Ollama not running (`ollama serve`), model not "
            f"pulled (`ollama pull {model}`), or a docling-graph config key "
            "changed in a newer version (see README, Version note)."
        )


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
        yield "Pick a bike first (or build one in the 'Your manual' tab).", "", ""
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


def build_app(answer_model: str, extract_model: str, cfg: config.Config) -> gr.Blocks:
    with gr.Blocks(title="Torque to Me") as app:
        gr.Markdown(
            "# Torque to Me\n"
            "A maintenance assistant for old motorcycles, built from their "
            "scanned service manuals. Upload yours, get a knowledge graph, "
            "ask questions. Every answer is grounded: you see the exact "
            "facts and manual pages it came from. Runs fully local, your "
            "manual never leaves this machine."
        )

        with gr.Tab("Torque to me"):
            with gr.Row():
                bikes = list_bikes()
                bike_dd = gr.Dropdown(
                    choices=bikes,
                    value=(bikes[0][1] if bikes else None),
                    label="Bike",
                    scale=3,
                )
                refresh_btn = gr.Button("Refresh list", scale=1)
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

            refresh_btn.click(lambda: gr.update(choices=list_bikes()), outputs=bike_dd)
            # functools.partial, not a lambda: Gradio only streams the
            # generator's yields if it can see a generator function.
            gr.on(
                [ask_btn.click, question.submit],
                functools.partial(answer, model=answer_model, cfg=cfg),
                inputs=[bike_dd, question],
                outputs=[answer_box, subgraph_box, facts_box],
            )

        with gr.Tab("Your manual"):
            gr.Markdown(
                "Upload one **chapter** of your bike's service manual "
                "(use `torque split` to cut it out; the "
                "maintenance chapter with the torque tables is the best "
                "start). Whole manuals work but take much longer and "
                "extract worse."
            )
            pdf_in = gr.File(label="Service manual chapter (PDF)", file_types=[".pdf"])
            with gr.Row():
                name_in = gr.Textbox(
                    label="Bike name", placeholder="e.g. Honda NX650 RD08", scale=3
                )
                chapter_in = gr.Textbox(
                    label="Chapter (optional)",
                    placeholder="e.g. Lubrication — auto-detected if left empty",
                    scale=2,
                )
            build_btn = gr.Button("Build knowledge graph", variant="primary")
            status = gr.Textbox(label="Status", lines=8, interactive=False)
            build_btn.click(
                functools.partial(ingest, model=extract_model, cfg=cfg),
                inputs=[pdf_in, name_in, chapter_in],
                outputs=status,
            )

    return app


def run(args: argparse.Namespace) -> None:
    OUTPUTS.mkdir(exist_ok=True)
    bikes = list_bikes()
    print(
        f"Found {len(bikes)} bike graph(s): {', '.join(label for label, _ in bikes) or 'none yet'}"
    )
    print(f"Answering with {args.answer_model}, extracting with {args.extract_model}")
    build_app(args.answer_model, args.extract_model, args.cfg).launch(
        server_port=args.port,
        favicon_path=str(ICON) if ICON.exists() else None,
    )
