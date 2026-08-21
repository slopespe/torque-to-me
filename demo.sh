#!/bin/bash
# One-command demo launcher: ./demo.sh [answer-model]
# Starts the Torque to Me app with the local graph(s) ready to query.
# Models come from config.toml; the optional argument overrides the
# answer model for this run.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "No .venv found. Run the Setup section of the README first."
    exit 1
fi
if [ ! -x .venv/bin/torque ]; then
    echo "The 'torque' command is not installed in .venv. Run: .venv/bin/pip install -e ."
    exit 1
fi
if ! curl -s http://localhost:11434 > /dev/null; then
    echo "Ollama is not running. Start the Ollama app first (or 'ollama serve')."
    exit 1
fi

# First run: seed the bundled example graph so there is something to query.
if ! ls outputs/*/graph.pickle > /dev/null 2>&1; then
    echo "No graphs in outputs/ yet — seeding the Honda NX650 example."
    mkdir -p outputs
    cp -R examples/honda-nx650 outputs/demo
fi

ANSWER_MODEL="${1:-$(.venv/bin/python -c "
from torque_to_me.config import load
print(load().answer.model)")}"

if ! ollama list | grep -q "^${ANSWER_MODEL}"; then
    echo "Answer model '$ANSWER_MODEL' not found in Ollama. Available:"
    ollama list
    exit 1
fi

echo "Starting Torque to Me (answering with '$ANSWER_MODEL') — open http://localhost:7860"
exec .venv/bin/torque app --answer-model "$ANSWER_MODEL"
