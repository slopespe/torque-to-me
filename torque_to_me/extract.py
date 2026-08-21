"""
Run the docling-graph pipeline on a manual chapter with a local Ollama
model, then persist the knowledge graph and an extraction report.

Usage:
    torque extract data/input/chapter_maintenance.pdf --model qwen3.5-32k

Outputs (per manual, under outputs/<tag>/):
    graph.pickle          NetworkX DiGraph (used by query/app/viz)
    models.json           Raw extracted objects for spot-checking
    extraction_report.txt Node/edge counts and sample provenance

Note on config keys: the run_pipeline config occasionally changes between
docling-graph versions (this repo pins >=1.9,<2). The dict below follows
the documented API. If a key is rejected, check the current README:
https://github.com/docling-project/docling-graph
"""

import argparse
import json
import pickle
import sys
from collections import Counter

from docling_graph import PipelineContext, run_pipeline

from torque_to_me import bike_meta
from torque_to_me.graph_enrich import enrich
from torque_to_me.templates.service_manual import ServiceManualChapter


def run(args: argparse.Namespace) -> None:
    if not args.pdf.exists():
        sys.exit(f"File not found: {args.pdf}")

    tag = args.tag or args.pdf.stem
    args.outdir = args.outdir / tag

    config = {
        "source": str(args.pdf),
        "template": ServiceManualChapter,
        "backend": "llm",
        "inference": "local",
        "processing_mode": "many-to-one",  # merge whole chapter into one root object
        "extraction_contract": args.contract,
        # ollama_chat (not ollama): LiteLLM's ollama/ route uses the legacy
        # generate endpoint, which returns empty content for thinking models
        # (e.g. qwen3.5) — the chat endpoint separates thinking from content.
        "provider_override": "ollama_chat",
        "model_override": args.model,
        "structured_output": True,
        "use_chunking": True,
        # Leave room for thinking tokens; the library's registry fallback
        # (4092) truncates thinking models mid-reasoning.
        # Ollama serves one request at a time, so parallel workers only queue
        # up and trip the timeout; a single worker with a generous timeout is
        # faster in practice for local thinking models.
        "parallel_workers": args.cfg.extract.parallel_workers,
        "llm_overrides": {
            "max_output_tokens": args.cfg.extract.max_output_tokens,
            "reliability": {"timeout_s": args.cfg.extract.timeout_s},
        },
    }

    print(f"Running pipeline on {args.pdf} with ollama/{args.model} ...")
    print("(This is the slow step: minutes to tens of minutes depending on hardware.)\n")

    context: PipelineContext = run_pipeline(config)

    graph = context.knowledge_graph
    models = context.extracted_models

    # Recover cross-links the LLM left as prose (procedure text -> entity
    # name matches); see graph_enrich.py.
    enrich_stats = enrich(graph)
    print(f"Enrichment added edges: {enrich_stats}")

    args.outdir.mkdir(parents=True, exist_ok=True)

    # 1. Persist the graph for the query layer
    graph_path = args.outdir / "graph.pickle"
    with open(graph_path, "wb") as f:
        pickle.dump(graph, f)

    bike_meta.write(
        args.outdir,
        name=args.name or tag.replace("-", " "),
        chapter=args.chapter or bike_meta.chapter_from_graph(graph),
    )

    # 2. Dump raw extracted objects for manual spot-checking
    models_path = args.outdir / "models.json"
    dumped = [m.model_dump() for m in models]
    models_path.write_text(json.dumps(dumped, indent=2, ensure_ascii=False, default=str))

    # 3. Extraction report
    type_counts = Counter(
        data.get("__label__", data.get("label", type(data).__name__))
        if isinstance(data, dict)
        else "unknown"
        for _, data in graph.nodes(data=True)
    )
    edge_counts = Counter(
        data.get("label", data.get("type", "EDGE")) for _, _, data in graph.edges(data=True)
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
