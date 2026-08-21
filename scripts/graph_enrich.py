#!/usr/bin/env python3
"""
Deterministic graph enrichment: recover cross-links that the LLM captured
as prose instead of filling the relational fields.

Small local models reliably extract entities and step text but often leave
the nested relationship lists empty (e.g. a procedure's step says
"Crankcase drain plug torque: 25 N·m" while its torque_specs list is []).
Since both endpoints already exist as nodes, the links can be recovered by
string-matching entity names against each procedure's text — no LLM call.

Adds (skipping edges that already exist):
    Procedure -SPECIFIES->  TorqueSpec   fastener named in procedure text
    Procedure -REQUIRES->   Part         part named in procedure text
    Symptom   -RESOLVED_BY-> Procedure   procedure subject named in symptom text

Derived edges carry {'derived': 'text-match'} so they stay distinguishable
from LLM-extracted ones.

Usage (existing outputs, no re-extraction):
    python scripts/graph_enrich.py --tag demo
"""

import argparse
import pickle
import re
import sys
from pathlib import Path

# Generic action words stripped from procedure titles when matching them
# against symptom text ("OIL PUMP SERVICING" should match on "oil pump").
_TITLE_STOPWORDS = {
    "servicing", "service", "inspection", "inspect", "cleaning", "clean",
    "check", "checking", "replacement", "replace", "adjustment", "adjust",
    "removal", "installation", "and", "or", "the",
}

_MIN_PHRASE_LEN = 4  # ignore matches on very short fragments


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _contains(needle: str, haystack: str) -> bool:
    """Substring match that also tolerates spacing differences
    ('down tube' matches 'downtube')."""
    if needle in haystack:
        return True
    return needle.replace(" ", "") in haystack.replace(" ", "")


def _procedure_text(data: dict) -> str:
    parts = [data.get("title") or ""]
    parts.extend(data.get("steps") or [])
    parts.extend(data.get("tools") or [])
    return _norm(" ".join(parts))


def _title_subject(title: str) -> str:
    words = [w for w in _norm(title).split() if w not in _TITLE_STOPWORDS]
    return " ".join(words)


def enrich(graph) -> dict:
    """Add derived edges in place; returns counts per edge label."""
    by_label: dict[str, list] = {}
    for node, data in graph.nodes(data=True):
        by_label.setdefault(data.get("label", ""), []).append((node, data))

    stats = {"SPECIFIES": 0, "REQUIRES": 0, "RESOLVED_BY": 0}

    def add(src, dst, label):
        if src != dst and not graph.has_edge(src, dst):
            graph.add_edge(src, dst, label=label, derived="text-match")
            stats[label] += 1

    procedures = [(n, d, _procedure_text(d)) for n, d in by_label.get("Procedure", [])]

    for spec_node, spec in by_label.get("TorqueSpec", []):
        fastener = _norm(spec.get("fastener") or "")
        if len(fastener) < _MIN_PHRASE_LEN:
            continue
        for proc_node, _, text in procedures:
            if _contains(fastener, text):
                add(proc_node, spec_node, "SPECIFIES")

    for part_node, part in by_label.get("Part", []):
        name = _norm(part.get("name") or "")
        if len(name) < _MIN_PHRASE_LEN:
            continue
        for proc_node, _, text in procedures:
            if _contains(name, text):
                add(proc_node, part_node, "REQUIRES")

    for sym_node, sym in by_label.get("Symptom", []):
        sym_text = _norm(
            " ".join([sym.get("description") or ""] + (sym.get("possible_causes") or []))
        )
        for proc_node, proc, _ in procedures:
            subject = _title_subject(proc.get("title") or "")
            if len(subject) >= _MIN_PHRASE_LEN and _contains(subject, sym_text):
                add(sym_node, proc_node, "RESOLVED_BY")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Add derived cross-link edges to an extracted graph")
    parser.add_argument("--tag", default=None, help="Manual tag, e.g. 'demo' (reads outputs/<tag>/graph.pickle)")
    parser.add_argument("--graph", type=Path, default=None, help="Explicit path to a graph.pickle")
    args = parser.parse_args()

    if args.graph:
        graph_path = args.graph
    elif args.tag:
        graph_path = Path("outputs") / args.tag / "graph.pickle"
    else:
        sys.exit("Provide --tag or --graph")

    if not graph_path.exists():
        sys.exit(f"Graph not found: {graph_path}")

    with open(graph_path, "rb") as f:
        graph = pickle.load(f)

    before = graph.number_of_edges()
    stats = enrich(graph)

    with open(graph_path, "wb") as f:
        pickle.dump(graph, f)

    print(f"Enriched {graph_path}: {before} -> {graph.number_of_edges()} edges")
    for label, count in stats.items():
        print(f"  +{count} {label}")


if __name__ == "__main__":
    main()
