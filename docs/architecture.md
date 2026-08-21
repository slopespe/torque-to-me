# Architecture

The README covers *how to use* the pipeline; this document covers *why it
is built the way it is*. Code references are to modules in
`torque_to_me/`.

## Design goals

1. **Fully local.** A scanned service manual never leaves the machine:
   OCR (Docling), extraction and answering (Ollama) all run on localhost.
2. **Every fact traceable.** Answers exist to be *verified against the
   paper manual*, not trusted — so every node carries page-level
   provenance, and the UI shows the exact facts behind each answer.
3. **Small models, honest division of labor.** LLMs do what they are
   good at (reading prose, filling a schema); plain code does what it is
   good at (linking, retrieval, rendering); a human spot-check is the
   final quality gate at each stage.

## Components

```
cli.py ──dispatch──▶ split_pdf ─▶ conversion_check ─▶ extract ─▶ query / app / visualize
                                                        │
                                     graph_enrich ◀─────┘ (auto-run)
                                     curate_demo  (optional, human pass)

config.py     config.toml loading, precedence: defaults < file/env < CLI flags
bike_meta.py  per-bike meta.json + graph path resolution (shared by query/viz)
graph_viz.py  pyvis rendering (shared by app's provenance panel and viz)
templates/service_manual.py  the extraction schema — see below
```

`cli.py` owns every argument definition and dispatches lazily
(`importlib.import_module` at run time), so `torque split --help` never
pays the multi-second import cost of gradio or docling. This is a
load-bearing property: `torque_to_me/__init__.py` must stay import-light.

## Extraction: a Pydantic template as the contract

`templates/service_manual.py` defines four entities — `Part`,
`TorqueSpec`, `Symptom`, `Procedure` — under a `ServiceManualChapter`
root. Two design points:

- **The `description=` strings are the extraction instructions.** The
  LLM sees them verbatim; improving them is the main quality lever, ahead
  of switching models.
- **`graph_id_fields` make node IDs stable across chunks**, so the same
  fastener mentioned in a procedure and in a torque table merges into one
  node instead of duplicating.

The schema is deliberately small: four entity types is enough, and more
types measurably dilute extraction quality with small local models.

Extraction runs through docling-graph with `provider_override:
"ollama_chat"` (the legacy `ollama/` LiteLLM route returns empty content
for thinking models) and `parallel_workers: 1` (Ollama serves one request
at a time; parallel workers only queue and trip timeouts). Both were
debugged the hard way — see the README's lessons-learned section.

## Enrichment: deterministic, not another LLM pass

Small local models reliably extract entities and step text but tend to
leave the *relational* fields empty: a step says "Crankcase drain plug
torque: 25 N·m" while the procedure's `torque_specs` list stays `[]`.
Since both endpoints already exist as nodes, `graph_enrich.py` recovers
the edges by string-matching entity names against procedure text — no
LLM call, instant, and reproducible. Derived edges carry
`derived="text-match"` so they never masquerade as extracted ones; the
same marker discipline applies to the human pass (`curate_demo.py`,
`match="curated"`).

## Retrieval: keyword overlap, on purpose

`query.py` scores nodes by stopword-filtered keyword overlap with the
question, takes the top N, and expands one hop along the graph (a
procedure pulls in its torque specs and parts; a symptom pulls in its
resolutions). No embeddings, no vector store. At the scale of a manual
chapter (tens of nodes) keyword overlap retrieves as well as embeddings
would, is transparent (you can see exactly why a node matched), and adds
zero dependencies or model downloads. The subgraph is serialized as
numbered plain-text facts with provenance, and the answer model is
instructed to use *only* those facts and cite the pages.

## Two models, two jobs

- **Extraction** wants a strong (usually thinking) model with a large
  context — docling-graph cannot pass per-request options to Ollama, so
  the context must be baked into a derived model (e.g. `qwen3.5-32k`;
  Ollama's default 4096 silently truncates extraction prompts).
- **Answering** wants latency: a fast model with thinking disabled
  answers in seconds. `stream_ollama` passes `num_ctx` per request,
  streams thinking/response chunks separately (so the UI can show
  progress during a thinking model's minutes-long reasoning), and retries
  without `think` for models that reject it.

Both are set in `config.toml`; `config.py` implements the precedence
chain (built-in defaults < `config.toml`/`TORQUE_TO_ME_CONFIG` < CLI
flags) and warns on unknown keys so typos don't silently fall back to
defaults.

## Storage

One directory per bike under `outputs/<tag>/`: `graph.pickle` (the
NetworkX graph the query layer loads), `models.json` (raw extracted
objects, the spot-checkable form), `extraction_report.txt`, and
`meta.json` (display name + chapter, `bike_meta.py`). Pickle is a
pragmatic choice for a local-only tool — the graphs contain only plain
dicts and strings — but treat pickles as trusted input: load only graphs
you built yourself.
