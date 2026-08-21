"""Configuration for Torque to Me.

Precedence, lowest to highest:
  1. Built-in defaults (the dataclasses below)
  2. config.toml at the project root (or the file named by the
     TORQUE_TO_ME_CONFIG environment variable)
  3. CLI flags (each script passes explicit values over these)

Every key in config.toml is optional; unknown keys produce a warning so
typos don't silently fall back to defaults.
"""

import os
import sys
from dataclasses import dataclass, fields
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

ROOT = Path(__file__).resolve().parents[1]
ENV_VAR = "TORQUE_TO_ME_CONFIG"


@dataclass(frozen=True)
class OllamaConfig:
    url: str = "http://localhost:11434"


@dataclass(frozen=True)
class AnswerConfig:
    model: str = "gemma4:12b"
    # Thinking mode sent to Ollama: false = answer immediately (seconds),
    # true = reason first (minutes). Leave unset in config.toml for models
    # that don't support thinking (e.g. gemma3) — although an unsupported
    # value is retried without it automatically.
    think: bool | str | None = None
    # The facts prompt alone is ~4k tokens; Ollama's 4096 default would
    # silently truncate it.
    num_ctx: int = 16384
    timeout_s: int = 900
    top_nodes: int = 4  # seed nodes retrieved per question


@dataclass(frozen=True)
class ExtractConfig:
    model: str = "qwen3.5-32k"
    max_output_tokens: int = 16000
    timeout_s: int = 900
    # Local Ollama serves one request at a time; more workers just queue
    # and trip timeouts.
    parallel_workers: int = 1


@dataclass(frozen=True)
class Config:
    ollama: OllamaConfig
    answer: AnswerConfig
    extract: ExtractConfig
    source: Path | None  # the file the overrides came from, if any


def _build(section_cls, data: dict, section: str):
    known = {f.name for f in fields(section_cls)}
    unknown = set(data) - known
    if unknown:
        print(
            f"config: ignoring unknown key(s) in [{section}]: {', '.join(sorted(unknown))}",
            file=sys.stderr,
        )
    return section_cls(**{k: v for k, v in data.items() if k in known})


def load(path: str | Path | None = None) -> Config:
    """Load configuration; missing file or keys fall back to defaults."""
    candidate = Path(path or os.environ.get(ENV_VAR) or ROOT / "config.toml")
    raw = {}
    if candidate.exists():
        if tomllib is None:
            print(
                f"config: found {candidate} but TOML parsing needs Python 3.11+ "
                "(or `pip install tomli`); using built-in defaults",
                file=sys.stderr,
            )
        else:
            with open(candidate, "rb") as f:
                raw = tomllib.load(f)
    elif path or os.environ.get(ENV_VAR):
        sys.exit(f"config: file not found: {candidate}")

    for section in set(raw) - {"ollama", "answer", "extract"}:
        print(f"config: ignoring unknown section [{section}]", file=sys.stderr)

    return Config(
        ollama=_build(OllamaConfig, raw.get("ollama", {}), "ollama"),
        answer=_build(AnswerConfig, raw.get("answer", {}), "answer"),
        extract=_build(ExtractConfig, raw.get("extract", {}), "extract"),
        source=candidate if raw else None,
    )
