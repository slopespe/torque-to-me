#!/usr/bin/env python3
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
    python scripts/05_app.py --model qwen2.5:14b
    # then open http://localhost:7860
"""

import argparse
import importlib.util
import pickle
import re
import shutil
import sys
from pathlib import Path

import gradio as gr
import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Import the query module (filename starts with a digit, so load by path)
_spec = importlib.util.spec_from_file_location(
    "query_layer", Path(__file__).resolve().parent / "04_query.py"
)
q = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(q)

OUTPUTS = ROOT / "outputs"

EXAMPLES = [
    "What is the torque for the rear axle nut?",
    "How do I adjust the valve clearance?",
    "The engine runs rich at idle, what should I check?",
    "What oil does the engine take and how much?",
    "When should the drive chain be replaced?",
]


# ----------------------------------------------------------------------
# Graph registry
# ----------------------------------------------------------------------

def list_bikes() -> list[str]:
    return sorted(p.parent.name for p in OUTPUTS.glob("*/graph.pickle"))


def load_graph(tag: str) -> nx.DiGraph:
    with open(OUTPUTS / tag / "graph.pickle", "rb") as f:
        return pickle.load(f)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "my-bike"


# ----------------------------------------------------------------------
# Ingestion (upload -> knowledge graph)
# ----------------------------------------------------------------------

def ingest(pdf_file, bike_name: str, model: str):
    """Run the docling-graph pipeline on an uploaded manual."""
    if pdf_file is None:
        yield "Upload a PDF first."
        return
    if not bike_name or not bike_name.strip():
        yield "Give the bike a name first (e.g. 'Honda NX650')."
        return

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
        from docling_graph import run_pipeline
        from templates.service_manual import ServiceManualChapter

        config = {
            "source": str(dest),
            "template": ServiceManualChapter,
            "backend": "llm",
            "inference": "local",
            "processing_mode": "many-to-one",
            "extraction_contract": "dense",
            # ollama_chat: the legacy ollama/ route returns empty content
            # for thinking models (see scripts/03_extract.py).
            "provider_override": "ollama_chat",
            "model_override": model,
            "structured_output": True,
            "use_chunking": True,
            # Single worker + long timeout: Ollama serves one request at a
            # time (see scripts/03_extract.py).
            "parallel_workers": 1,
            "llm_overrides": {
                "max_output_tokens": 16000,
                "reliability": {"timeout_s": 900},
            },
        }
        context = run_pipeline(config)
        graph = context.knowledge_graph

        # Recover cross-links the LLM left as prose (see graph_enrich.py).
        from graph_enrich import enrich
        enrich(graph)

        with open(outdir / "graph.pickle", "wb") as f:
            pickle.dump(graph, f)

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

def answer(tag: str, question: str, model: str):
    question = (question or "").strip()
    if not tag:
        return "Pick a bike first (or build one in the 'Your manual' tab).", ""
    if not question:
        return "Ask a maintenance question.", ""

    graph = load_graph(tag)
    ranked = q.score_nodes(graph, question)
    if not ranked:
        return "Nothing in this manual's graph matches that question.", ""

    seeds = [node_id for node_id, _ in ranked[:4]]
    nodes = q.collect_subgraph(graph, seeds)
    facts = q.format_facts(graph, nodes)
    bike = tag.replace("-", " ")
    prompt = q.PROMPT_TEMPLATE.format(facts=facts, question=question, bike=bike)
    try:
        reply = q.ask_ollama(model, prompt).strip()
    except Exception as e:  # noqa: BLE001
        reply = f"Ollama call failed: {e}\nIs `ollama serve` running?"
    return reply, facts


# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------

def build_app(model: str) -> gr.Blocks:
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
                bike_dd = gr.Dropdown(
                    choices=list_bikes(),
                    value=(list_bikes()[0] if list_bikes() else None),
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
                    facts_box = gr.Textbox(
                        label="Retrieved graph facts (provenance)",
                        lines=22,
                        interactive=False,
                    )

            refresh_btn.click(
                lambda: gr.update(choices=list_bikes()), outputs=bike_dd
            )
            ask_btn.click(
                lambda tag, qn: answer(tag, qn, model),
                inputs=[bike_dd, question],
                outputs=[answer_box, facts_box],
            )
            question.submit(
                lambda tag, qn: answer(tag, qn, model),
                inputs=[bike_dd, question],
                outputs=[answer_box, facts_box],
            )

        with gr.Tab("Your manual"):
            gr.Markdown(
                "Upload one **chapter** of your bike's service manual "
                "(use `scripts/01_split_pdf.py` to cut it out; the "
                "maintenance chapter with the torque tables is the best "
                "start). Whole manuals work but take much longer and "
                "extract worse."
            )
            pdf_in = gr.File(label="Service manual chapter (PDF)", file_types=[".pdf"])
            name_in = gr.Textbox(
                label="Bike name", placeholder="e.g. Honda NX650 Dominator"
            )
            build_btn = gr.Button("Build knowledge graph", variant="primary")
            status = gr.Textbox(label="Status", lines=8, interactive=False)
            build_btn.click(
                lambda f, n: ingest(f, n, model),
                inputs=[pdf_in, name_in],
                outputs=status,
            )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Torque to Me demo UI")
    parser.add_argument("--model", default="qwen2.5:14b", help="Ollama model")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    OUTPUTS.mkdir(exist_ok=True)
    bikes = list_bikes()
    print(f"Found {len(bikes)} bike graph(s): {', '.join(bikes) or 'none yet'}")
    build_app(args.model).launch(server_port=args.port)


if __name__ == "__main__":
    main()
