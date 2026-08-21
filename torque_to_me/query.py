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
    torque query "torque for the rear axle nut"
    torque query "how do I adjust valve clearance" --model gemma3:12b
    # model, thinking mode, context size etc. come from config.toml
    torque query "engine runs rich at idle" --show-facts
"""

import argparse
import json
import pickle
import re
import sys

import networkx as nx
import requests

from torque_to_me import bike_meta, config

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


def format_provenance(prov) -> str:
    """Render a docling-graph provenance record as a short human cite."""
    if not prov:
        return ""
    if isinstance(prov, dict):
        parts = []
        pages = prov.get("pages")
        if pages:
            word = "page" if len(pages) == 1 else "pages"
            parts.append(f"{word} " + ", ".join(str(p) for p in pages))
        if prov.get("manual_section"):
            parts.append(prov["manual_section"])
        if prov.get("match") == "curated":
            parts.append("curated")
        return f"  (source: {'; '.join(parts)})" if parts else ""
    return f"  (source: {prov})"


def format_value(value) -> str:
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    return str(value)


def format_facts(graph: nx.DiGraph, nodes: set[str]) -> str:
    """Serialize nodes and their internal edges as numbered plain-text facts."""
    lines = []
    index = {}
    for i, node_id in enumerate(sorted(nodes), start=1):
        index[node_id] = i
        data = graph.nodes[node_id]
        kind = data.get("__class__") or data.get("label") or "Fact"
        attrs = {
            k: v for k, v in data.items()
            if not k.startswith("__")
            and k not in ("id", "type", "label")
            and v not in (None, [], "")
        }
        body = "; ".join(f"{k}={format_value(v)}" for k, v in attrs.items())
        lines.append(f"[{i}] {kind}: {body}{format_provenance(data.get('__provenance__'))}")
    for u, v, edata in graph.edges(nodes, data=True):
        if u in nodes and v in nodes:
            label = edata.get("label", edata.get("type", "related to"))
            lines.append(f"    [{index[u]}] --{label}--> [{index[v]}]")
    return "\n".join(lines)


def stream_ollama(model: str, prompt: str, cfg: config.Config):
    """Yield ("thinking" | "response", chunk) pairs as Ollama streams them.

    Thinking models reason for minutes before the first response token;
    streaming lets callers show progress instead of a dead UI.
    """
    answer = cfg.answer
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"num_ctx": answer.num_ctx},
    }
    if answer.think is not None:
        payload["think"] = answer.think

    resp = requests.post(
        f"{cfg.ollama.url}/api/generate",
        json=payload,
        stream=True,
        timeout=(10, answer.timeout_s),
    )
    if resp.status_code == 400 and "think" in payload and "think" in resp.text:
        # Model doesn't support thinking modes (e.g. gemma3) — retry without.
        del payload["think"]
        resp = requests.post(
            f"{cfg.ollama.url}/api/generate",
            json=payload,
            stream=True,
            timeout=(10, answer.timeout_s),
        )
    with resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            data = json.loads(line)
            if data.get("thinking"):
                yield "thinking", data["thinking"]
            if data.get("response"):
                yield "response", data["response"]
            if data.get("done"):
                return


PROMPT_TEMPLATE = """You are a maintenance assistant for the motorcycle "{bike}".
Answer the question using ONLY the facts below, extracted from the service manual.
Rules:
- If the facts do not contain the answer, say so plainly. Do not guess.
- Quote exact values (torque, clearances, intervals) as they appear in the facts.
- End with a "Source:" line listing the manual page numbers given in the facts you used (e.g. "Source: pages 1, 3").

FACTS:
{facts}

QUESTION: {question}

ANSWER:"""


def run(args: argparse.Namespace) -> None:
    args.graph = bike_meta.resolve_graph_path(args.tag, args.graph)

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
    thinking_noted = False
    for kind, chunk in stream_ollama(args.model, prompt, args.cfg):
        if kind == "thinking":
            if not thinking_noted:
                print("(model is thinking...)", file=sys.stderr)
                thinking_noted = True
            continue
        print(chunk, end="", flush=True)
    print()
