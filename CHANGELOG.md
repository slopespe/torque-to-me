# Changelog

All notable changes to this project are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-08-21

First tagged release.

### Added

- End-to-end local pipeline for scanned motorcycle service manuals:
  Docling conversion, LLM extraction into a Pydantic template
  (docling-graph 1.x), knowledge graph with page-level provenance,
  keyword retrieval with one-hop subgraph expansion, grounded answering
  via Ollama.
- `torque` CLI (`pip install -e .`) with subcommands `split`, `check`,
  `extract`, `enrich`, `curate-demo`, `query`, `viz`, `app` — replacing
  the earlier numbered scripts.
- Gradio app with upload-and-build and ask tabs, streaming answers, and a
  graphical provenance panel (pyvis subgraph + the exact facts used).
- Deterministic graph enrichment: cross-links recovered by string-matching
  entity names against procedure text, marked `derived="text-match"`.
- Hand-curated demo pass (`torque curate-demo`) with `match="curated"`
  provenance markers.
- `config.toml` configuration layer (defaults < file/`TORQUE_TO_ME_CONFIG`
  < CLI flags) with unknown-key warnings; two-model split — fast
  answering model, large-context extraction model.
- Bundled example: the Honda NX650 RD08 lubrication-chapter graph under
  `examples/honda-nx650/`, auto-seeded into `outputs/` by `demo.sh`.
- Unit tests for the pure-logic layers (config precedence, enrichment
  matching, retrieval and fact formatting, metadata) and GitHub Actions
  CI running ruff + pytest on Python 3.10–3.12.
- Architecture documentation in `docs/architecture.md`.
