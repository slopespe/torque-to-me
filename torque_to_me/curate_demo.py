"""
Hand-curated additions to a demo graph: the human-in-the-loop pass.

The LLM extraction (Stage 2) is good at entities and step text but a small
local model misses some structure: whole procedures merged into neighbours,
consumables like the recommended oil never becoming nodes, and causes
mis-filed as symptoms. This script encodes what a careful human reading of
the converted manual (outputs/conversion_preview.md) recovers, with page
provenance. Values below were read from the Honda NX650 chapter 2
(LUBRICATION); manual page 2-N corresponds to PDF page N.

Curated nodes/edges carry match='curated' / derived='curated' so they stay
distinguishable from LLM-extracted ones.

Usage (after `torque extract`, idempotent):
    torque curate-demo --tag demo
"""

import argparse
import pickle
import sys
from pathlib import Path


def prov(doc_id, pages, section):
    return {"document_id": doc_id, "match": "curated", "pages": pages,
            "manual_section": section}


def find(graph, label, **match):
    for n, d in graph.nodes(data=True):
        if d.get("label") == label and all(d.get(k) == v for k, v in match.items()):
            return n
    raise KeyError(f"{label} {match}")


def curate(graph) -> None:
    doc_id = next(
        (d.get("__provenance__", {}).get("document_id")
         for _, d in graph.nodes(data=True)
         if isinstance(d.get("__provenance__"), dict)
         and d["__provenance__"].get("document_id")),
        "demo",
    )

    def add_part(slug, name, specification, pages, section):
        nid = f"Part_curated_{slug}"
        graph.add_node(nid, id=nid, label="Part", type="entity", __class__="Part",
                       name=name, part_number=None, specification=specification,
                       __provenance__=prov(doc_id, pages, section))
        return nid

    def add_procedure(slug, title, steps, pages, section):
        nid = f"Procedure_curated_{slug}"
        graph.add_node(nid, id=nid, label="Procedure", type="entity",
                       __class__="Procedure", title=title, steps=steps,
                       interval=None, tools=[], required_parts=[], torque_specs=[],
                       __provenance__=prov(doc_id, pages, section))
        return nid

    def edge(src, dst, label):
        if not graph.has_edge(src, dst):
            graph.add_edge(src, dst, label=label, derived="curated")

    chapter = find(graph, "ServiceManualChapter", chapter_title="LUBRICATION")

    # Parts the extraction missed
    engine_oil = add_part(
        "engine_oil", "engine oil",
        "Honda 4-Stroke Oil or equivalent; API SE or SF; SAE 10W-40 or 20W-50 "
        "(use 10W-40 below 0°C / 32°F). Capacity: 2.3 L at engine assembly, "
        "1.9 L at oil change, 1.95 L at oil and filter change.",
        [1], "SPECIFICATIONS (2-1)")
    oil_filter = add_part(
        "oil_filter_element", "oil filter element",
        "Replace with new element; install with the 'OUT SIDE' mark facing out.",
        [4], "ENGINE OIL FILTER REPLACEMENT (2-4)")
    sealing_washer = add_part(
        "drain_plug_sealing_washer", "drain plug sealing washer",
        "Check condition after draining; replace if damaged.",
        [3], "ENGINE OIL CHANGE (2-3)")
    oil_seal = add_part(
        "oil_pump_oil_seal", "oil pump oil seal",
        "AFTER '88: replace if worn or damaged; install squarely at "
        "0.5-1.1 mm (0.020-0.043 in) depth from the outer surfaces.",
        [], "OIL PUMP (2-5 ff.)")

    # Procedures the extraction missed
    oil_change = add_procedure(
        "engine_oil_change", "ENGINE OIL CHANGE",
        ["Change the oil with the engine warm and the motorcycle on its side "
         "stand for complete and rapid draining.",
         "Remove the oil filler cap and the drain plugs on the frame down tube "
         "and the left crankcase.",
         "After the oil has drained, check that the drain plug sealing washers "
         "are in good condition, then install the plugs. Crankcase drain plug: "
         "25 N·m; down tube drain plug: 35 N·m.",
         "If the oil filter and strainer are also scheduled, service them "
         "before filling the frame oil tank.",
         "Pour one liter of recommended oil into the oil tank (total capacity "
         "at oil change is about 1.9 L, but not all fits initially).",
         "Start the engine and let it idle for a few minutes.",
         "Install the oil filler cap/dipstick, stop the engine, and add oil up "
         "to the upper level mark with the motorcycle upright."],
        [3], "ENGINE OIL CHANGE (2-3)")
    filter_repl = add_procedure(
        "oil_filter_replacement", "ENGINE OIL FILTER REPLACEMENT",
        ["Change the oil filter before filling the frame oil tank with oil.",
         "Remove the oil filter cover from the right crankcase and remove the "
         "filter element; discard the element.",
         "Check that the O-ring on the oil filter cover is in good condition.",
         "Install the spring, a new oil filter element ('OUT SIDE' mark facing "
         "out) and the oil filter cover, aligning the tabs on the filter cover "
         "and right crankcase cover.",
         "Tighten the cover bolts. TORQUE: 9 N·m (0.9 kg-m, 7 ft-lb).",
         "Pour in the recommended oil to the upper level on the filler "
         "cap/dipstick."],
        [4], "ENGINE OIL FILTER REPLACEMENT (2-4)")
    check_bolt = add_procedure(
        "crankcase_oil_check_bolt", "CRANKCASE OIL CHECK BOLT",
        ["The check bolt verifies the lubrication system: the oil pump keeps "
         "the crankcase at the proper level, so a wrong level here means part "
         "of the lubrication system is not working properly.",
         "Run the engine, stop it and wait a few minutes, then remove the oil "
         "check bolt.",
         "The crankcase oil level is correct if oil is flush with the bottom "
         "of the check bolt hole.",
         "Install the oil check bolt and recheck the level with the oil filler "
         "cap/dipstick."],
        [3, 4], "CRANKCASE OIL CHECK BOLT (2-3/2-4)")

    for p in (oil_change, filter_repl, check_bolt):
        edge(chapter, p, "CONTAINS")

    # Cross-links
    edge(oil_change, find(graph, "TorqueSpec", fastener="Crankcase drain plug"), "SPECIFIES")
    edge(oil_change, find(graph, "TorqueSpec", fastener="Down tube drain plug"), "SPECIFIES")
    edge(filter_repl, find(graph, "TorqueSpec", fastener="Oil filter cover bolt"), "SPECIFIES")

    edge(oil_change, engine_oil, "REQUIRES")
    edge(oil_change, sealing_washer, "REQUIRES")
    edge(filter_repl, oil_filter, "REQUIRES")
    edge(filter_repl, engine_oil, "REQUIRES")

    level_check = find(graph, "Procedure", title="ENGINE OIL LEVEL CHECK")
    oil_pump = find(graph, "Procedure", title="OIL PUMP SERVICING")
    # every procedure that says "fill with the recommended oil"
    for title in ("ENGINE OIL LEVEL CHECK", "OIL STRAINER SCREEN CLEANING",
                  "OIL STRAINER NUT CLEANING/INSPECTION", "OIL PUMP SERVICING"):
        try:
            edge(find(graph, "Procedure", title=title), engine_oil, "REQUIRES")
        except KeyError:
            pass
    edge(oil_pump, oil_seal, "REQUIRES")

    # Symptom -> fix links the manual implies
    edge(find(graph, "Symptom", description="Oil level too low"), level_check, "RESOLVED_BY")
    edge(find(graph, "Symptom", description="Oil contamination"), oil_change, "RESOLVED_BY")
    edge(find(graph, "Symptom", description="Low oil pressure"), check_bolt, "RESOLVED_BY")

    # Causes mis-extracted as standalone symptoms (already listed under
    # "Oil level too low" possible_causes)
    for desc in ("External oil leaks", "Worn piston rings"):
        try:
            graph.remove_node(find(graph, "Symptom", description=desc))
        except KeyError:
            pass


def run(args: argparse.Namespace) -> None:
    graph_path = Path("outputs") / args.tag / "graph.pickle"
    if not graph_path.exists():
        sys.exit(f"Graph not found: {graph_path}. Run `torque extract` first.")

    with open(graph_path, "rb") as f:
        graph = pickle.load(f)

    before = (graph.number_of_nodes(), graph.number_of_edges())
    curate(graph)

    with open(graph_path, "wb") as f:
        pickle.dump(graph, f)

    print(f"Curated {graph_path}: {before[0]} -> {graph.number_of_nodes()} nodes, "
          f"{before[1]} -> {graph.number_of_edges()} edges")
