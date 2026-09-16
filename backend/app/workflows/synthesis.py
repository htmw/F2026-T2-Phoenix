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
                "summary": output.summary or _short_label(output.payload),
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
    """The human-readable result — prefer deliverables over one-line summaries."""
    for node in plan.nodes:
        output = outputs.get(node.key)
        if output is None or not output.succeeded:
            continue
        document = output.payload.get("document")
        if isinstance(document, str) and document.strip():
            return document.strip()

    # Single successful agent: surface its full deliverable, not a collage heading.
    succeeded = [
        outputs[node.key]
        for node in plan.nodes
        if node.key in outputs and outputs[node.key].succeeded
    ]
    if len(succeeded) == 1:
        body = _deliverable(succeeded[0].payload)
        if body:
            return body

    sections: list[str] = []
    for node in plan.nodes:
        output = outputs.get(node.key)
        if output is None or not output.succeeded:
            continue
        body = _deliverable(output.payload)
        if body:
            sections.append(f"## {output.agent_id}\n{body}")
    if sections:
        return "\n\n".join(sections)
    return "The workflow completed but no agent produced a readable result."


def _deliverable(payload: dict[str, object]) -> str:
    """Prefer the substantive payload the operator asked for over a short summary."""
    for key in ("answer", "document", "content", "code", "report"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    changes = payload.get("changes")
    if isinstance(changes, list) and changes:
        blocks: list[str] = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            file_name = str(change.get("file") or "file")
            action = str(change.get("action") or "change")
            content = change.get("content")
            diff = change.get("diff")
            explanation = change.get("explanation")
            header = f"### {action} `{file_name}`"
            if isinstance(content, str) and content.strip():
                lang = _fence_lang(file_name)
                blocks.append(f"{header}\n\n```{lang}\n{content.rstrip()}\n```")
            elif isinstance(diff, str) and diff.strip():
                blocks.append(f"{header}\n\n```diff\n{diff.rstrip()}\n```")
            elif isinstance(explanation, str) and explanation.strip():
                blocks.append(f"{header}\n\n{explanation.strip()}")
        if blocks:
            summary = payload.get("summary")
            if isinstance(summary, str) and summary.strip():
                return summary.strip() + "\n\n" + "\n\n".join(blocks)
            return "\n\n".join(blocks)

    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list) and artifacts:
        blocks = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            name = str(artifact.get("name") or "artifact")
            content = artifact.get("content")
            if isinstance(content, str) and content.strip():
                lang = _fence_lang(name)
                blocks.append(f"### `{name}`\n\n```{lang}\n{content.rstrip()}\n```")
        if blocks:
            summary = payload.get("summary")
            if isinstance(summary, str) and summary.strip():
                return summary.strip() + "\n\n" + "\n\n".join(blocks)
            return "\n\n".join(blocks)

    findings = payload.get("findings")
    if isinstance(findings, list) and findings:
        lines = [str(item) for item in findings if str(item).strip()]
        if lines:
            return "\n".join(f"- {line}" for line in lines)

    return _short_label(payload)


def _short_label(payload: dict[str, object]) -> str:
    for key in ("summary", "assessment", "rationale"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    findings = payload.get("findings")
    if isinstance(findings, list):
        return f"{len(findings)} finding(s)."
    return ""


def _fence_lang(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".py"):
        return "python"
    if lower.endswith((".ts", ".tsx")):
        return "typescript"
    if lower.endswith((".js", ".jsx")):
        return "javascript"
    if lower.endswith((".md", ".markdown")):
        return "markdown"
    if lower.endswith((".json",)):
        return "json"
    if lower.endswith((".yml", ".yaml")):
        return "yaml"
    if lower.endswith((".sh", ".bash")):
        return "bash"
    if lower.endswith((".rs",)):
        return "rust"
    if lower.endswith((".go",)):
        return "go"
    return ""
