# Example: Honda NX650 RD08 — Lubrication chapter

A complete, real output of the pipeline: the knowledge graph built from
the lubrication chapter of a 1996 Honda NX650 Dominator service manual
(extracted with `qwen3.5-32k` on a laptop, then enriched and hand-curated
— see `torque curate-demo`). The manual itself is not included; service
manuals are copyrighted. These files are the *extracted facts*, each with
page-level provenance back to the source.

| File | What it is |
|---|---|
| `graph.pickle` | The NetworkX knowledge graph the query layer runs on (31 nodes, 47 edges) |
| `models.json` | Raw extracted objects — the spot-checkable form of the graph |
| `extraction_report.txt` | Node/edge counts and sample provenance from the extraction run |
| `graph.html` | Interactive pyvis view — download and open in a browser |
| `meta.json` | Bike display name and chapter |

## Try it without extracting anything

Copy the example into `outputs/` and every command works immediately:

```bash
cp -R examples/honda-nx650 outputs/demo
torque query "what is the torque for the oil drain plug?" --tag demo
torque viz --tag demo
torque app        # or ./demo.sh, which seeds outputs/ from here automatically
```

(Answering still needs Ollama and the answer model — see the README —
but retrieval, provenance and the graph view work with no model at all:
add `--show-facts` to `torque query` to see what the LLM would be given.)

## A word of caution

These values were spot-checked against the paper manual, but verify any
torque figure yourself before putting a wrench on a real bike. That is
what the page numbers are for.
