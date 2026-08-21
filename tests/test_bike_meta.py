"""Per-bike metadata and graph-path resolution."""

import networkx as nx
import pytest

from torque_to_me import bike_meta


def test_chapter_from_graph_title_cases_all_caps():
    g = nx.DiGraph()
    g.add_node("root", chapter_title="LUBRICATION")
    assert bike_meta.chapter_from_graph(g) == "Lubrication"


def test_chapter_from_graph_keeps_mixed_case_and_handles_absence():
    g = nx.DiGraph()
    g.add_node("root", chapter_title="Engine Removal")
    assert bike_meta.chapter_from_graph(g) == "Engine Removal"
    assert bike_meta.chapter_from_graph(nx.DiGraph()) is None


def test_label_uses_meta_json(tmp_path):
    bike_meta.write(tmp_path, name="Honda NX650 RD08", chapter="Lubrication")
    assert bike_meta.label(tmp_path) == "Honda NX650 RD08 — Lubrication"


def test_label_falls_back_to_directory_name(tmp_path):
    bike_dir = tmp_path / "honda-nx650"
    bike_dir.mkdir()
    assert bike_meta.label(bike_dir) == "honda nx650"


def test_load_returns_empty_dict_on_corrupt_json(tmp_path):
    (tmp_path / bike_meta.META_FILENAME).write_text("{not json")
    assert bike_meta.load(tmp_path) == {}


def _make_graph_dir(outputs, tag):
    graph_dir = outputs / tag
    graph_dir.mkdir(parents=True)
    (graph_dir / "graph.pickle").write_bytes(b"")
    return graph_dir / "graph.pickle"


def test_resolve_graph_path_uses_single_existing_graph(tmp_path):
    only = _make_graph_dir(tmp_path, "demo")
    assert bike_meta.resolve_graph_path(None, None, outputs=tmp_path) == only


def test_resolve_graph_path_by_tag(tmp_path):
    _make_graph_dir(tmp_path, "demo")
    wanted = _make_graph_dir(tmp_path, "nx650")
    assert bike_meta.resolve_graph_path("nx650", None, outputs=tmp_path) == wanted


def test_resolve_graph_path_exits_when_ambiguous_or_missing(tmp_path):
    with pytest.raises(SystemExit):
        bike_meta.resolve_graph_path(None, None, outputs=tmp_path)  # none exist
    _make_graph_dir(tmp_path, "a")
    _make_graph_dir(tmp_path, "b")
    with pytest.raises(SystemExit):
        bike_meta.resolve_graph_path(None, None, outputs=tmp_path)  # ambiguous
    with pytest.raises(SystemExit):
        bike_meta.resolve_graph_path("missing", None, outputs=tmp_path)
