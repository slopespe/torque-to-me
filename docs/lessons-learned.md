# Torque to Me — Lessons Learned

Notes from building a local, offline knowledge-graph pipeline over motorcycle
service manuals (docling-graph + Ollama) on a 24 GB Apple Silicon Mac.

All numbers below come from actual run logs, not estimates.

---

## 1. Time: small local LLMs are slow per page — and the LLM is not the only cost

Measured on a 24 GB Mac, Ollama, `parallel_workers = 1`:

| Run | Input | Model | Wall clock | Result |
|---|---|---|---|---|
| Demo | 13-page scanned chapter | `qwen3.5-32k` | ~40 min | 26 nodes / 25 edges |
| NX650 schedule | **1 page**, one big table | `qwen3.5-32k` | ~7 min (Phase 1 alone 2:51) | 2 nodes / 1 edge |
| NX650 schedule | same page | `gemma4-12b-32k` | **497 s** (8:17) — docling ~1.5 min, skeleton 6:55, fill 1:10 | 2 nodes / 1 edge |

Working rule: **3–8 minutes per page**, end to end. It does not collapse for a
short document — a single page still cost 8 minutes, because the pipeline is
fixed-cost per document (OCR -> chunk -> skeleton pass -> fill pass), not per word.

Consequences:

- A full 300-page service manual is a **20–40 hour** job on this hardware.
  Local extraction is an overnight batch process, not an interactive one.
- The extract-once / query-forever split is the right architecture. Extraction
  is a slow offline cost; querying the resulting graph is instant (~1 s to
  retrieve facts). You pay hours once so answers cost seconds forever. That is
  the entire argument for putting a graph between the manual and the user.
- Ollama serves one request at a time, so `parallel_workers > 1` buys nothing —
  requests queue and trip timeouts. The only real levers on wall clock are a
  smaller model or fewer pages.

## 2. Thinking vs non-thinking: ~30x on answering, ~nothing on extraction

**On answering, it is decisive.** `qwen3.5` in thinking mode took 2–5 minutes
per question. `gemma4:12b` with `think = false` answers in 4–8 seconds — same
graph, same facts, same question. For a demo where someone types "what oil does
it take?", 4 seconds is a product and 3 minutes is a broken app. Hence
`think = false` in `config.toml`.

**On extraction, thinking bought nothing.** Both models returned the identical
2-node graph from the schedule page, and the thinking model was actually faster
on Phase 1 (2:51 vs 6:55). Reasoning helps when the task is to work something
out; structured extraction into a fixed schema is mostly transcription. What
extraction needs is a **large context window and instruction-following
discipline**, not a reasoning budget.

Related trap: Ollama's default 4096-token context **silently truncates** instead
of erroring (`prompt_tokens=4095, completion_tokens=1, finish=length`, which
surfaced as "LiteLLM returned empty content"). With small local models the
failure mode is usually silent truncation, not a stack trace.

## 3. Templates are the main quality lever — the model can only fill boxes you gave it

The maintenance-schedule page produced 2 nodes not because the model was dumb,
but because **`ServiceManualChapter` had no box for a schedule row**. Its
entities were Procedure / Part / TorqueSpec / Symptom. Faced with a 30-row
maintenance matrix, the model's only legal move was to squeeze it into one
`Procedure` — and it did, with the step list `["USA only."]`, which is
footnote 6.

Garbage output, correct behaviour. The fix was a template change, not a model
change: a new `MaintenanceItem` entity (`item`, `action`, `interval`, `note`,
`page_ref`) with `graph_id_fields: ["item"]`, plus an instruction on the edge to
emit one entry **per row** and not summarize the table.

Two rules confirmed:

- **Field descriptions are prompts.** "Spell out the code letters from the
  legend (I=inspect, C=clean, R=replace)" does more for output quality than
  swapping a 12B model for a 30B one.
- **Keep the schema small.** Every extra entity type dilutes attention. Five
  entity types is about the ceiling for a 12B model.

## 4. The real bottleneck is upstream of the LLM: table extraction

This is the lesson to put first in any public write-up. Here is what the LLM
actually received for that page (`outputs/conversion_preview.md`):

```
|       |                  | NOTES | x 1,000 mi | 0.6 | 4        | 8 | 12   | 16 | 20   | 24 |
| ITEMS |                  | NOTES | x 1,000 mi | 1   | 4        | 8 | 12   | 25.6 | 20 | 38.4 | Refer
|       | FUEL LINE        |       |            |     | 6.4 12.8 | 1 | 19.2 | 1  | 32.0 | 1  | to page 3-4 |
|       | VALVE CLEARANCE  |       |            | 1   | 1        | 一 | I    | 1  | 1    | 1  | 3-6 |
```

- **`I` is unreadable.** The most meaningful symbol in the table comes back as
  `1`, `I`, `l`, or the CJK character `一`, at random. "Inspect" vs. "nothing"
  becomes a coin flip.
- **Columns shifted.** The km header row leaked into the FUEL LINE row
  (`6.4 12.8`, `19.2`, `32.0`), and the mileage headers are garbled (`25.6`,
  `38.4` where `16`, `24` belong).
- **Reading order scrambled.** Footnotes came out 2, 4, 3, 5, 7, 6 — which is
  exactly why note 6, "USA only.", became the procedure's only step.
- RapidOCR returned an empty result on the first pass entirely.

A matrix table encodes meaning in **2D position**: row x column = do this at
that mileage. Serializing it to linear markdown destroys that relationship
before the LLM ever sees it. No model upgrade fixes a corrupted input. Options:
a better table-structure model in docling, feeding the page image to a vision
model, or hand-authoring that one table.

## 5. Repetitive documents are the sweet spot — with one qualifier

Repetition helps for three concrete reasons:

1. **One template covers the whole document.** Schema-design cost is paid once
   and amortized over hundreds of pages, instead of needing a new entity type
   per chapter.
2. **`graph_id_fields` do real work.** When "Oil filter bolt" appears on pages
   3, 7 and 40, stable IDs merge it into one node with three provenance
   references. Repetition *builds* the graph instead of fragmenting it.
3. **The model settles into a groove.** Consistent page structure means
   consistent chunk shapes, which means consistent output — the run-to-run
   variance that plagues one-off pages largely disappears.

The qualifier: **repetitive in reading order, not repetitive on a grid.** A
parts catalogue, a torque table listed as `bolt — size — Nm` rows, a procedure
repeated per component — those linearize cleanly and the pipeline eats them. A
maintenance matrix looks repetitive to a human eye but is really a 2D
cross-reference, and it is the hardest thing to get through docling intact.
Service manuals contain both.

## 6. The one found the hard way: thermal emergency sleep

Long local runs put the Mac into **Thermal Emergency Sleep** — confirmed at
13:57, 14:49 and repeatedly 00:30–00:38 (`pmset -g log | grep -i thermal`). All
DarkWake events: lid closed / display asleep on AC, where macOS force-sleeps
rather than ramping the fans. A 40-minute run that saturates the GPU needs the
lid open and `caffeinate -dimsu`, or the machine quietly stops the job for you.
