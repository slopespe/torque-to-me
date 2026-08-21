"""
Extraction template for the motorcycle service manual.

This file defines BOTH the extraction schema (what the LLM pulls out of
the manual) and the resulting graph structure (entities become nodes,
edge() fields become typed relationships).

Design notes:
- `description=` strings are extraction instructions: the LLM sees them.
  Be literal and concrete. Improving these is the main quality lever.
- `graph_id_fields` make node IDs stable across chunks, so the same part
  or procedure mentioned twice merges into one node.
- Keep the schema small. Four entities is enough for the demo; more
  entity types dilute extraction quality.
"""

from pydantic import BaseModel, Field


def edge(label: str, *, description: str = ""):
    """List field that becomes a typed graph edge: docling-graph reads
    json_schema_extra['edge_label'] when converting models to the graph."""
    return Field(
        default_factory=list,
        description=description,
        json_schema_extra={"edge_label": label},
    )


class Part(BaseModel):
    """A physical part or consumable referenced in the manual."""

    model_config = {
        "is_entity": True,
        "graph_id_fields": ["name"],
    }

    name: str = Field(
        description=(
            "Name of the part or consumable exactly as written in the "
            "manual, e.g. 'spark plug', 'oil filter', 'drive chain'."
        )
    )
    part_number: str | None = Field(
        default=None,
        description=(
            "Manufacturer part number if printed in the manual, e.g. "
            "'15410-MB0-003'. Leave empty if not stated."
        ),
    )
    specification: str | None = Field(
        default=None,
        description=(
            "Type or spec of the part if stated, e.g. spark plug type "
            "'DPR8EA-9', oil grade 'SAE 10W-40'. Leave empty if not stated."
        ),
    )


class TorqueSpec(BaseModel):
    """A tightening torque value for a specific fastener."""

    model_config = {
        "is_entity": True,
        "graph_id_fields": ["fastener"],
    }

    fastener: str = Field(
        description=(
            "The bolt, nut or fastener the torque applies to, exactly as "
            "named in the manual, e.g. 'rear axle nut', 'oil drain bolt', "
            "'cylinder head cover bolt'."
        )
    )
    value_nm: float = Field(
        description=(
            "Torque value in Newton-metres (N·m). If the manual gives "
            "kgf·m, convert: 1 kgf·m = 9.807 N·m. If a range is given, "
            "use the midpoint."
        )
    )
    thread_size: str | None = Field(
        default=None,
        description="Thread size if stated, e.g. 'M8', '10 mm'.",
    )


class Symptom(BaseModel):
    """A fault, symptom or problem described in troubleshooting content."""

    model_config = {
        "is_entity": True,
        "graph_id_fields": ["description"],
    }

    description: str = Field(
        description=(
            "Short description of the symptom or fault as the rider would "
            "observe it, e.g. 'engine runs rich at idle', 'hard starting "
            "when cold', 'excessive chain noise'."
        )
    )
    possible_causes: list[str] = Field(
        default_factory=list,
        description=(
            "Possible causes listed in the manual for this symptom, "
            "one string per cause."
        ),
    )


class Procedure(BaseModel):
    """A maintenance or repair procedure with ordered steps."""

    model_config = {
        "is_entity": True,
        "graph_id_fields": ["title"],
    }

    title: str = Field(
        description=(
            "Title of the procedure as written in the manual, e.g. "
            "'Valve clearance inspection and adjustment', 'Engine oil "
            "and filter change'."
        )
    )
    steps: list[str] = Field(
        default_factory=list,
        description=(
            "The procedure steps in order, one string per step, "
            "paraphrased briefly but keeping all numeric values "
            "(clearances, capacities, temperatures) exact."
        ),
    )
    interval: str | None = Field(
        default=None,
        description=(
            "Service interval if stated, e.g. 'every 12 000 km', "
            "'every 2 years'. Leave empty if not stated."
        ),
    )
    tools: list[str] = Field(
        default_factory=list,
        description="Special tools required, if the manual lists any.",
    )
    required_parts: list[Part] = edge(
        "REQUIRES",
        description="Parts and consumables this procedure uses or replaces.",
    )
    torque_specs: list[TorqueSpec] = edge(
        "SPECIFIES",
        description="Torque values that apply within this procedure.",
    )


class ServiceManualChapter(BaseModel):
    """Root object: one chapter of a motorcycle service manual."""

    chapter_title: str = Field(
        description="Title of the chapter, e.g. 'Maintenance'."
    )
    procedures: list[Procedure] = edge(
        "CONTAINS",
        description="All maintenance/repair procedures in this chapter.",
    )
    torque_specs: list[TorqueSpec] = edge(
        "LISTS",
        description=(
            "Torque values from standalone torque tables in this chapter "
            "(values already captured inside a procedure may repeat here; "
            "that is fine, they merge by fastener name)."
        ),
    )
    symptoms: list[Symptom] = edge(
        "COVERS",
        description=(
            "Troubleshooting symptoms in this chapter. Empty list if the "
            "chapter has no troubleshooting content."
        ),
    )
    symptom_resolutions: list[Procedure] = edge(
        "RESOLVED_BY",
        description=(
            "Procedures that troubleshooting content points to as fixes. "
            "Only fill when the manual explicitly links a symptom to a "
            "procedure."
        ),
    )
