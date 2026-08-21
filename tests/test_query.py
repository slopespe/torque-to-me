"""Retrieval and fact-formatting logic (no LLM involved)."""

import networkx as nx

from torque_to_me.query import (
    collect_subgraph,
    format_facts,
    format_provenance,
    score_nodes,
    tokenize,
)


def test_tokenize_drops_stopwords_and_lowercases():
    assert tokenize("What is the torque for the rear axle nut?") == {
        "torque",
        "rear",
        "axle",
        "nut",
    }


def test_score_nodes_ranks_by_keyword_overlap():
    g = nx.DiGraph()
    g.add_node("close", label="TorqueSpec", fastener="rear axle nut")
    g.add_node("far", label="Procedure", title="rear brake adjustment")
    g.add_node("none", label="Part", name="oil filter")
    ranked = score_nodes(g, "rear axle torque")
    assert [node for node, _ in ranked] == ["close", "far"]
    assert ranked[0][1] == 2 / 3  # 'rear' + 'axle' out of 3 question tokens
    assert ranked[1][1] == 1 / 3


def test_score_nodes_skips_nodes_with_only_internal_attrs():
    g = nx.DiGraph()
    g.add_node("hidden", __provenance__={"pages": [1]})
    assert score_nodes(g, "pages") == []


def test_collect_subgraph_takes_one_hop_both_directions():
    g = nx.DiGraph()
    g.add_edge("seed", "out")
    g.add_edge("in", "seed")
    g.add_edge("out", "two-hops-away")
    assert collect_subgraph(g, ["seed"]) == {"seed", "out", "in"}


def test_format_facts_numbers_nodes_and_renders_internal_edges():
    g = nx.DiGraph()
    g.add_node("a", label="Part", name="bolt", part_number=None)
    g.add_node("b", label="TorqueSpec", fastener="axle nut", value_nm=88.0)
    g.add_node("c", label="Part", name="outside")
    g.add_edge("a", "b", label="SPECIFIES")
    g.add_edge("a", "c", label="REQUIRES")

    facts = format_facts(g, {"a", "b"})
    assert "[1] Part: name=bolt" in facts
    assert "[2] TorqueSpec: fastener=axle nut; value_nm=88.0" in facts
    assert "[1] --SPECIFIES--> [2]" in facts
    assert "outside" not in facts  # edges to nodes outside the subgraph are omitted


def test_format_provenance_renders_pages_section_and_curated():
    prov = {"pages": [1, 3], "manual_section": "LUBRICATION (2-1)", "match": "curated"}
    assert format_provenance(prov) == "  (source: pages 1, 3; LUBRICATION (2-1); curated)"


def test_format_provenance_single_page_and_empty():
    assert format_provenance({"pages": [3]}) == "  (source: page 3)"
    assert format_provenance(None) == ""
    assert format_provenance({}) == ""
