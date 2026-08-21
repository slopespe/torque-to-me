#!/usr/bin/env python3
"""
Run the docling-graph pipeline on a manual chapter with a local Ollama
model, then persist the knowledge graph and an extraction report.

Usage:
    python scripts/03_extract.py data/input/chapter_maintenance.pdf \
        --model qwen2.5:14b

Outputs:
    outputs/graph.pickle          NetworkX DiGraph (used by 04/05/06)
    outputs/models.json           Raw extracted objects for spot-checking
    outputs/extraction_report.txt Node/edge counts and sample provenance

Note on config keys: docling-graph is a young library (0.2.x) and the
run_pipeline config occasionally changes between versions. The dict below
follows the documented API. If a key is rejected, check the current README:
https://github.com/docling-project/docling-graph
"""

import argparse
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

# Make templates/ importable when run from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from templates.service_manual import ServiceManualChapter  # noqa: E402

from docling_graph import PipelineContext, run_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract knowledge graph from manual chapter")
    parser.add_argument("pdf", type=Path, help="Chapter PDF")
    parser.add_argument("--model", default="qwen2.5:14b", help="Ollama model name")
    parser.add_argument(
        "--contract",
        default="dense",
        choices=["auto", "dense"],
        help="Extraction contract; 'dense' = skeleton-then-flesh, better for complex docs",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Name for this manual, e.g. 'honda-nx650'. Defaults to the PDF filename. "
        "Outputs go to outputs/<tag>/ so multiple bikes can coexist.",
    )
    parser.add_argument("--outdir", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(f"File not found: {args.pdf}")

    tag = args.tag or args.pdf.stem
    args.outdir = args.outdir / tag

    config = {
        "source": str(args.pdf),
        "template": ServiceManualChapter,
        "backend": "llm",
        "inference": "local",
        "processing_mode": "many-to-one",   # merge whole chapter into one root object
        "extraction_contract": args.contract,
        "provider_override": "ollama",
        "model_override": args.model,       # LiteLLM routes ollama/<model>
        "structured_output": True,
        "use_chunking": True,
    }

    print(f"Running pipeline on {args.pdf} with ollama/{args.model} ...")
    print("(This is the slow step: minutes to tens of minutes depending on hardware.)\n")

    context: PipelineContext = run_pipeline(config)

    graph = context.knowledge_graph
    models = context.extracted_models

    args.outdir.mkdir(parents=True, exist_ok=True)

    # 1. Persist the graph for the query layer
    graph_path = args.outdir / "graph.pickle"
    with open(graph_path, "wb") as f:
        pickle.dump(graph, f)

    # 2. Dump raw extracted objects for manual spot-checking
    models_path = args.outdir / "models.json"
    dumped = [m.model_dump() for m in models]
    models_path.write_text(json.dumps(dumped, indent=2, ensure_ascii=False, default=str))

    # 3. Extraction report
    type_counts = Counter(
        data.get("__label__", data.get("label", type(data).__name__))
        if isinstance(data, dict) else "unknown"
        for _, data in graph.nodes(data=True)
    )
    edge_counts = Counter(
        data.get("label", data.get("type", "EDGE"))
        for _, _, data in graph.edges(data=True)
    )

    lines = [
        f"Source: {args.pdf}",
        f"Model:  ollama/{args.model}  contract={args.contract}",
        "",
        f"Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges",
        "",
        "Nodes by type:",
        *(f"  {t}: {c}" for t, c in type_counts.most_common()),
        "",
        "Edges by type:",
        *(f"  {t}: {c}" for t, c in edge_counts.most_common()),
        "",
        "Sample nodes with provenance:",
    ]
    for node_id, data in list(graph.nodes(data=True))[:5]:
        prov = data.get("__provenance__", "n/a")
        lines.append(f"  {node_id}")
        lines.append(f"    provenance: {prov}")

    report_path = args.outdir / "extraction_report.txt"
    report_path.write_text("\n".join(lines))

    print(f"Graph:  {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print(f"Saved:  {graph_path}")
    print(f"        {models_path}")
    print(f"        {report_path}")
    print("\nGATE: open models.json, pick 10 facts (torque values, intervals),")
    print("check them against the paper manual. Target 9/10 correct before Stage 3.")


if __name__ == "__main__":
    main()
