"""Assembling a coherent final answer from agent outputs.

A workflow's last node is not automatically "the answer": documentation may have been
skipped, a branch may have failed, and a join may have several terminals. This module
turns that into one record that names its contributors and is honest about what is
missing — silently omitting a skipped agent would make a partial run look complete.
"""

from __future__ import annotations

from app.schemas.execution import AgentOutput
from app.schemas.workflow import WorkflowPlan


def synthesise(
    plan: WorkflowPlan,
    outputs: dict[str, AgentOutput],
    skipped: dict[str, str],
    *,
    total_cost_usd: float,
) -> dict[str, object]:
    """Build the workflow's final result.

    Prefers a documentation agent's ``document`` when one exists, because that agent is
    the one whose job is to write for a reader. Otherwise the terminal payloads are
    presented with attribution. Either way, skipped and failed nodes are listed, not
    dropped.
    """
    contributors: list[dict[str, object]] = []
    for node in plan.nodes:
        output = outputs.get(node.key)
        if output is None or not output.succeeded:
            continue
        contributors.append(
            {
                "node_key": node.key,
                "agent_id": output.agent_id,
                "summary": output.summary or _fallback_summary(output.payload),
            }
        )

    failed = {
        key: (output.error.message if output.error else output.status.value)
        for key, output in outputs.items()
        if not output.succeeded
    }
    partial = bool(skipped or failed)

    sources = {edge.source for edge in plan.edges}
    terminal = [node.key for node in plan.nodes if node.key not in sources]
    terminal_payloads = {
        key: outputs[key].payload for key in terminal if key in outputs and outputs[key].succeeded
    }

    return {
        "answer": _answer(plan, outputs),
        "contributors": contributors,
        "skipped": dict(skipped),
        "failed": failed,
        "partial": partial,
        "nodes": terminal_payloads,
        "cost_usd": round(total_cost_usd, 6),
        "agents_run": [outputs[key].agent_id for key in outputs if outputs[key].succeeded],
    }


def _answer(plan: WorkflowPlan, outputs: dict[str, AgentOutput]) -> str:
    """The human-readable result, preferring an agent's own document over a collage."""
    for node in plan.nodes:
        output = outputs.get(node.key)
        if output is None or not output.succeeded:
            continue
        document = output.payload.get("document")
        if isinstance(document, str) and document.strip():
            return document.strip()

    sections: list[str] = []
    for node in plan.nodes:
        output = outputs.get(node.key)
        if output is None or not output.succeeded:
            continue
        summary = output.summary or _fallback_summary(output.payload)
        if summary:
            sections.append(f"## {output.agent_id}\n{summary}")
    if sections:
        return "\n\n".join(sections)
    return "The workflow completed but no agent produced a readable summary."


def _fallback_summary(payload: dict[str, object]) -> str:
    for key in ("summary", "assessment", "rationale"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    findings = payload.get("findings")
    if isinstance(findings, list):
        return f"{len(findings)} finding(s)."
    return ""
