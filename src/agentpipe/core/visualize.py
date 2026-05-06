"""DAG visualization: render a pipeline as ASCII art or Mermaid diagram."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentpipe.core.pipeline import Pipeline


def render_ascii(pipeline: Pipeline) -> str:
    """Render the pipeline DAG as an ASCII diagram.

    Output looks like:

        [research]
            |
        [write-code]  [write-tests]
            |              |
            +----- + ------+
                   |
             [integrate]

    Tasks are grouped by execution level (topological sort).
    Edges with conditions show the condition expression.
    """
    levels = pipeline.topological_sort()
    if not levels:
        return "(empty pipeline)"

    # Build edge info for labels
    edge_labels: dict[tuple[str, str], str] = {}
    for edge in pipeline.edges:
        label = ""
        if edge.condition and edge.condition.expression:
            label = f"[if {edge.condition.expression}]"
        edge_labels[(edge.upstream, edge.downstream)] = label

    lines: list[str] = []

    # Header
    lines.append(f"Pipeline: {pipeline.name}")
    lines.append(f"Strategy: {pipeline.execution_strategy.value}")
    lines.append("")

    for level_idx, level in enumerate(levels):
        # Render task boxes for this level
        boxes = []
        for task_name in level:
            task = pipeline.get_task(task_name)
            model = task.primary_model or "sub-pipeline"
            box = f"[ {task_name} ({model}) ]"
            boxes.append(box)

        row = "    ".join(boxes)
        lines.append(f"  {row}")

        # Render edges to next level
        if level_idx < len(levels) - 1:
            next_level = levels[level_idx + 1]
            edge_lines = []
            for src in level:
                for tgt in next_level:
                    key = (src, tgt)
                    if key in edge_labels:
                        label = edge_labels[key]
                        if label:
                            edge_lines.append(f"    {src} --> {tgt}  {label}")
                        else:
                            edge_lines.append(f"    {src} --> {tgt}")

            if edge_lines:
                # Draw connector
                lines.append("      |")
                for el in edge_lines:
                    lines.append(el)
                lines.append("      |")
            else:
                lines.append("      |")

    # Task details
    lines.append("")
    lines.append("Tasks:")
    for task in pipeline.tasks:
        perms = task.permissions
        allowed = [
            p
            for p in ["read", "edit", "write", "bash", "glob", "grep", "web_fetch"]
            if not perms.is_denied(_canonical_tool(p))
        ]
        perm_str = ", ".join(allowed) if allowed else "none"
        deps = ", ".join(task.depends_on) if task.depends_on else "(entry)"
        lines.append(
            f"  {task.name}: model={task.primary_model or 'N/A'}  "
            f"perms=[{perm_str}]  "
            f"depends_on={deps}  "
            f"max_iter={task.max_iterations}"
        )

    return "\n".join(lines)


def _canonical_tool(perm_field: str) -> str:
    """Map a short permission field name to the canonical tool name for is_denied()."""
    mapping = {
        "read": "file_read",
        "edit": "edit",
        "write": "file_write",
        "bash": "shell",
        "glob": "glob",
        "grep": "grep",
        "web_fetch": "web_fetch",
    }
    return mapping.get(perm_field, perm_field)


def render_mermaid(pipeline: Pipeline) -> str:
    """Render the pipeline DAG as a Mermaid flowchart.

    Output can be pasted into any Mermaid-compatible renderer
    (GitHub, Notion, Obsidian, mermaid.live, etc.).
    """
    lines = ["graph TD"]

    # Node definitions
    for task in pipeline.tasks:
        model = task.primary_model or "sub-pipeline"
        lines.append(f'    {_safe_id(task.name)}["{task.name}<br/>model: {model}"]')

    # Edges
    for edge in pipeline.edges:
        src = _safe_id(edge.upstream)
        tgt = _safe_id(edge.downstream)
        if edge.condition and edge.condition.expression:
            label = edge.condition.expression.replace('"', "'")
            lines.append(f'    {src} -->|"{label}"| {tgt}')
        else:
            lines.append(f"    {src} --> {tgt}")

    return "\n".join(lines)


def _safe_id(name: str) -> str:
    """Convert a task name to a valid Mermaid node ID."""
    return name.replace("-", "_").replace(" ", "_")
