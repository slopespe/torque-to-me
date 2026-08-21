#!/usr/bin/env python3
"""
Answer a maintenance question from the knowledge graph.

Pipeline per question:
  1. Score every node against the question (keyword overlap, cheap and
     transparent; no embeddings needed at this scale).
  2. Take the top nodes, expand one hop along their edges to collect a
     subgraph (a procedure pulls in its torque specs and parts, a
     symptom pulls in its resolutions).
  3. Serialize the subgraph as plain text facts, with provenance.
  4. Ask the local Ollama model to answer using ONLY those facts, citing
     pages.

Usage:
    python scripts/04_query.py "torque for the rear axle nut"
    python scripts/04_query.py "how do I adjust valve clearance" --model qwen2.5:14b
    python scripts/04_query.py "engine runs rich at idle" --show-facts
"""

import argparse
import pickle
import re
import sys
from pathlib import Path

import networkx as nx
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

STOPWORDS = {
    "the", "a", "an", "for", "of", "to", "on", "in", "is", "what", "how",
    "do", "i", "my", "and", "or", "at", "it", "with", "when", "should",
}


def tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS}


def node_text(data: dict) -> str:
    """Flatten a node's attributes into searchable text."""
    parts = []
    for key, value in data.items():
        if key.startswith("__"):
            continue
        if isinstance(value, (str, int, float)):
            parts.append(str(value))
        elif isinstance(value, list):
            parts.extend(str(v) for v in value if isinstance(v, (str, int, float)))
    return " ".join(parts)


def score_nodes(graph: nx.DiGraph, question: str) -> list[tuple[str, float]]:
    q_tokens = tokenize(question)
    scored = []
    for node_id, data in graph.nodes(data=True):
        n_tokens = tokenize(node_text(data))
        if not n_tokens:
            continue
        overlap = len(q_tokens & n_tokens)
        if overlap:
            scored.append((node_id, overlap / len(q_tokens)))
    return sorted(scored, key=lambda x: x[1], reverse=True)


def collect_subgraph(graph: nx.DiGraph, seeds: list[str]) -> set[str]:
    """Seeds plus one hop out and one hop in."""
    nodes = set(seeds)
    for s in seeds:
        nodes.update(graph.successors(s))
        nodes.update(graph.predecessors(s))
    return nodes


def format_facts(graph: nx.DiGraph, nodes: set[str]) -> str:
    """Serialize nodes and their internal edges as numbered plain-text facts."""
    lines = []
    idx = 1
    for node_id in nodes:
        data = graph.nodes[node_id]
        attrs = {
            k: v for k, v in data.items()
            if not k.startswith("__") and v not in (None, [], "")
        }
        prov = data.get("__provenance__")
        prov_s = f" [source: {prov}]" if prov else ""
        body = "; ".join(f"{k}={v}" for k, v in attrs.items())
        lines.append(f"[{idx}] {body}{prov_s}")
        idx += 1
    for u, v, edata in graph.edges(nodes, data=True):
        if u in nodes and v in nodes:
            label = edata.get("label", edata.get("type", "RELATED_TO"))
            lines.append(f"    edge: ({u}) -{label}-> ({v})")
    return "\n".join(lines)


def ask_ollama(model: str, prompt: str) -> str:
    resp = requests.post(
        OLLAMA_URL,
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["response"]


PROMPT_TEMPLATE = """You are a maintenance assistant for the motorcycle "{bike}".
Answer the question using ONLY the facts below, extracted from the service manual.
Rules:
- If the facts do not contain the answer, say so plainly. Do not guess.
- Quote exact values (torque, clearances, intervals) as they appear in the facts.
- End with a "Source:" line listing the page/chunk references from the facts.

FACTS:
{facts}

QUESTION: {question}

ANSWER:"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the maintenance knowledge graph")
    parser.add_argument("question", help="Maintenance question")
    parser.add_argument("--model", default="qwen2.5:14b", help="Ollama model")
    parser.add_argument(
        "--tag",
        default=None,
        help="Manual tag used at extraction (outputs/<tag>/graph.pickle). "
        "If omitted and exactly one graph exists, it is used.",
    )
    parser.add_argument("--graph", type=Path, default=None, help="Explicit graph path (overrides --tag)")
    parser.add_argument("--top", type=int, default=4, help="Seed nodes to retrieve")
    parser.add_argument("--show-facts", action="store_true", help="Print retrieved facts")
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

    bike = args.graph.parent.name.replace("-", " ").replace("_", " ")

    with open(args.graph, "rb") as f:
        graph: nx.DiGraph = pickle.load(f)

    ranked = score_nodes(graph, args.question)
    if not ranked:
        sys.exit("No matching nodes in the graph for that question.")

    seeds = [node_id for node_id, _ in ranked[: args.top]]
    subgraph_nodes = collect_subgraph(graph, seeds)
    facts = format_facts(graph, subgraph_nodes)

    if args.show_facts:
        print("--- Retrieved facts ---")
        print(facts)
        print("-----------------------\n")

    prompt = PROMPT_TEMPLATE.format(facts=facts, question=args.question, bike=bike)
    print(ask_ollama(args.model, prompt).strip())


if __name__ == "__main__":
    main()
