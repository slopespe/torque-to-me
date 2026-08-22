"""Torque to Me — a maintenance assistant for old motorcycles.

This module stays import-light on purpose: the CLI imports it before
dispatching, and subcommands like `torque split --help` must not pay the
multi-second import cost of gradio or docling.
"""

__version__ = "0.2.0"
