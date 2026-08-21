# Torque to Me

A maintenance assistant for old motorcycles, built from their scanned
service manuals with [docling-graph](https://github.com/docling-project/docling-graph).
Upload your own manual, get a knowledge graph, ask questions. Every answer
is grounded with page-level provenance back to the manual. Runs fully
local with Ollama: your manual never leaves your machine.

Works with any bike whose service manual you have as a PDF. Built and
tested on a 1990s Honda NX650 Dominator.

## How it works

```
scanned manual PDF
      │  Docling (OCR, layout, tables)
      ▼
structured document
      │  local LLM fills a Pydantic template (docling-graph)
      ▼
knowledge graph        Procedure ─REQUIRES→ Part
(every node carries    Procedure ─SPECIFIES→ TorqueSpec
 its source page)      Symptom ─RESOLVED_BY→ Procedure
      │
      ▼
question → matching nodes → one-hop subgraph → local LLM answers,
citing the manual pages it used
```

## Hardware requirements

- Python 3.10, 3.11 or 3.12
- 16 GB RAM minimum (32 GB comfortable)
- GPU with 8+ GB VRAM recommended. CPU-only works but extraction is slow.
- ~15 GB disk for models

## Setup

### 1. Install Ollama and pull a model

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh
# Windows/macOS: download from https://ollama.com/download

# Pick ONE based on your hardware:
ollama pull qwen2.5:14b     # best quality, needs ~10 GB VRAM
ollama pull qwen2.5:7b      # good compromise, ~6 GB VRAM
ollama pull granite3.1:8b   # IBM model, pairs well with docling

ollama run qwen2.5:14b "Say ok"   # verify
```

### 2. Create the Python environment

```bash
cd torque-to-me
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

First run of docling downloads its layout/OCR models (~500 MB).

### 3. Prepare your manual

Do NOT feed the whole manual on the first run. Cut out one chapter, ideally
the maintenance chapter with the torque tables:

```bash
python scripts/01_split_pdf.py data/input/manual.pdf --pages 20-45 \
    --output data/input/chapter_maintenance.pdf
```

Find the page range in the manual's table of contents.

## Two ways to use it

### Easy path: the app

```bash
python scripts/05_app.py --model qwen2.5:14b
# open http://localhost:7860
```

- **"Your manual" tab**: upload the chapter PDF, name the bike, click
  "Build knowledge graph". Extraction takes minutes to tens of minutes.
- **"Torque to me" tab**: pick the bike, ask away. The right panel shows
  the graph facts and manual pages behind each answer.

Multiple bikes coexist: each gets its own graph under `outputs/<bike-tag>/`.

### Full-control path: the scripts

Run in order; each stage has a quality gate.

**Stage 1 — Conversion check**

```bash
python scripts/02_conversion_check.py data/input/chapter_maintenance.pdf
```

Writes `outputs/conversion_preview.md`. **Gate:** torque tables must
survive as tables and numbers must be readable. If mangled, get a better
scan or try `pip install "docling-graph[vlm]"` and the VLM backend.
Nothing downstream recovers from bad conversion.

**Stage 2 — Extraction**

```bash
python scripts/03_extract.py data/input/chapter_maintenance.pdf \
    --model qwen2.5:14b --tag honda-nx650
```

Saves under `outputs/honda-nx650/`: `graph.pickle` (the graph),
`models.json` (raw extracted objects), `extraction_report.txt` (counts
and sample provenance). **Gate:** pick 10 facts from `models.json` and
check them against the paper manual. Target 9/10. If quality is poor,
improve the `description=` strings in `templates/service_manual.py`
(they are the extraction instructions the LLM sees), try a larger model,
or narrow the page range.

Alternative: induce a template from your own manual instead of using
the shipped one:

```bash
docling-graph template from-docs data/input/chapter_maintenance.pdf \
    --output templates/my_bike.py --name ServiceManualChapter --trial-run
```

**Stage 3 — Query from the terminal**

```bash
python scripts/04_query.py "torque for the rear axle nut" --tag honda-nx650
python scripts/04_query.py "engine runs rich at idle" --show-facts
```

(`--tag` optional when only one graph exists.)

**Stage 4 — Visualize the graph**

```bash
python scripts/06_visualize.py --tag honda-nx650
# open outputs/honda-nx650/graph.html
```

Interactive, color-coded by entity type. Hover a node to see its
attributes and source page.

## A word of caution

Extraction is good but not perfect. Spot-check torque values against the
paper manual before putting a wrench on your actual bike. The provenance
on every answer exists precisely so you can verify in seconds.

## Troubleshooting

| Problem | Fix |
|---|---|
| Ollama connection refused | `ollama serve` must be running; check `curl http://localhost:11434` |
| Extraction returns empty models | Model too small or chunk too large: try 14b, or a smaller page range |
| OCR garbage in conversion | Better scan, VLM extra, or pre-process the PDF (deskew, contrast) |
| `docling-graph` config key errors | Library is young (0.2.x), keys move between versions. Check `pip show docling-graph` and https://docling-project.github.io/docling-graph/ |
| Out of memory during extraction | Use the 7b model, or a smaller chapter |

## Project layout

```
torque-to-me/
├── README.md
├── requirements.txt
├── templates/
│   └── service_manual.py     # extraction schema (bike-agnostic)
├── scripts/
│   ├── 01_split_pdf.py       # cut a chapter out of the manual
│   ├── 02_conversion_check.py# Docling conversion preview (quality gate 1)
│   ├── 03_extract.py         # build the graph for one manual (--tag)
│   ├── 04_query.py           # CLI question answering
│   ├── 05_app.py             # Torque to Me app: upload, build, ask
│   └── 06_visualize.py       # interactive HTML graph view
├── data/input/               # your manual PDFs (gitignored)
└── outputs/<bike-tag>/       # one graph per bike (gitignored)
```

## Version note

Written against docling-graph 0.2.x (August 2026). The `run_pipeline`
config dict follows the documented API; if a key is rejected after a
library update, compare with the current README at
https://github.com/docling-project/docling-graph
