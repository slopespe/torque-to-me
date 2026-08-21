"""Deterministic enrichment: string-matching helpers and derived edges."""

import networkx as nx

from torque_to_me.graph_enrich import _contains, _title_subject, enrich


def test_contains_plain_substring():
    assert _contains("axle", "rear axle nut")
    assert not _contains("chain", "the oil pump")


def test_contains_tolerates_spacing_differences():
    assert _contains("down tube", "the downtube drain plug")
    assert _contains("downtube", "frame down tube")


def test_title_subject_strips_action_words():
    assert _title_subject("OIL PUMP SERVICING") == "oil pump"
    assert _title_subject("ENGINE OIL LEVEL CHECK") == "engine oil level"


def _graph():
    g = nx.DiGraph()
    g.add_node(
        "proc1",
        label="Procedure",
        title="ENGINE OIL CHANGE",
        steps=["Tighten the crankcase drain plug to 25 N·m."],
        tools=[],
    )
    g.add_node("spec1", label="TorqueSpec", fastener="Crankcase drain plug", value_nm=25.0)
    return g


def test_enrich_links_fastener_named_in_procedure_text():
    g = _graph()
    stats = enrich(g)
    assert stats["SPECIFIES"] == 1
    assert g.has_edge("proc1", "spec1")
    assert g.edges["proc1", "spec1"]["derived"] == "text-match"


def test_enrich_is_idempotent():
    g = _graph()
    enrich(g)
    stats = enrich(g)
    assert stats == {"SPECIFIES": 0, "REQUIRES": 0, "RESOLVED_BY": 0}


def test_enrich_skips_very_short_names():
    g = _graph()
    g.add_node("spec2", label="TorqueSpec", fastener="nut", value_nm=10.0)
    enrich(g)
    assert not g.has_edge("proc1", "spec2")


def test_enrich_links_part_named_in_procedure_text():
    g = _graph()
    g.add_node("part1", label="Part", name="drain plug")
    enrich(g)
    assert g.has_edge("proc1", "part1")
    assert g.edges["proc1", "part1"]["label"] == "REQUIRES"


def test_enrich_links_symptom_to_procedure_by_title_subject():
    g = _graph()
    g.add_node("proc2", label="Procedure", title="OIL PUMP SERVICING", steps=[], tools=[])
    g.add_node("sym1", label="Symptom", description="oil pump making noise", possible_causes=[])
    stats = enrich(g)
    assert stats["RESOLVED_BY"] == 1
    assert g.has_edge("sym1", "proc2")
