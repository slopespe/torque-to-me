"""Per-bike metadata stored next to each knowledge graph.

outputs/<tag>/meta.json holds what the directory name can't: the bike's
display name ("Honda NX650 RD08") and which manual chapter the graph was
built from ("Lubrication"). Written at extraction time; every field is
optional and the UI falls back to the tag.
"""

import json
from pathlib import Path

import networkx as nx

META_FILENAME = "meta.json"


def load(bike_dir: Path) -> dict:
    path = bike_dir / META_FILENAME
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def write(bike_dir: Path, name: str, chapter: str | None) -> None:
    meta = {"name": name}
    if chapter:
        meta["chapter"] = chapter
    (bike_dir / META_FILENAME).write_text(json.dumps(meta, indent=2) + "\n")


def chapter_from_graph(graph: nx.DiGraph) -> str | None:
    """The extraction template stores the chapter title on its root node."""
    for _, data in graph.nodes(data=True):
        title = data.get("chapter_title")
        if isinstance(title, str) and title.strip():
            title = title.strip()
            return title.title() if title.isupper() else title
    return None


def display_name(bike_dir: Path) -> str:
    return load(bike_dir).get("name") or bike_dir.name.replace("-", " ")


def label(bike_dir: Path) -> str:
    """Dropdown label: 'Honda NX650 RD08 — Lubrication'."""
    meta = load(bike_dir)
    name = meta.get("name") or bike_dir.name.replace("-", " ")
    chapter = meta.get("chapter")
    return f"{name} — {chapter}" if chapter else name
