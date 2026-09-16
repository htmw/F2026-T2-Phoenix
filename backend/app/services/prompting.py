"""Turning a structured ``AgentInput`` into prompts.

This is the one place where typed data becomes text. It exists as its own module so the
rule "agents exchange structured data, not transcripts" is enforceable by inspection:
only declared upstream payloads are rendered, and no conversation history exists to
accidentally forward.
"""

from __future__ import annotations

import json

from app.schemas.agent import AgentDefinition
from app.schemas.execution import AgentInput

MAX_UPSTREAM_CHARS = 20_000


def build_system_prompt(agent: AgentDefinition) -> str:
    """The agent's role plus the contract it must satisfy."""
    schema = json.dumps(agent.output_schema, indent=2, sort_keys=True)
    return (
        f"{agent.instructions}\n\n"
        "You work on a shared office floor with other specialist agents. Treat "
        "# Inbox and # Peer consult answers as authoritative teammate messages: "
        "honour task requests, incorporate answers, and do not ignore repair feedback.\n"
        "Upstream results and the organisational blackboard are how the hive "
        "shares state — build on them rather than redoing finished work.\n\n"
        "Respond with a single JSON object and nothing else: no prose before or after, "
        "no markdown code fences.\n"
        "The object must conform to this JSON Schema:\n"
        f"{schema}\n\n"
        "If you cannot complete the task, still return a conforming object and explain "
        "the limitation in its text fields. Never invent data to fill a field."
    )


def build_user_prompt(agent_input: AgentInput) -> str:
    """The objective, parameters, and upstream results — nothing else."""
    sections = [f"# Objective\n{agent_input.objective}"]

    if agent_input.parameters:
        sections.append(
            "# Parameters\n" + json.dumps(agent_input.parameters, indent=2, sort_keys=True)
        )

    for upstream in agent_input.upstream:
        payload = _render_payload(upstream.payload)
        sections.append(
            f"# Result from {upstream.agent_id} (node '{upstream.node_key}')\n{payload}"
        )

    if agent_input.context_notes:
        # May already include # Inbox / # Peer consult headings from the hive loop.
        notes = agent_input.context_notes.strip()
        if notes.startswith("# Inbox") or notes.startswith("# Peer consult"):
            sections.append(notes)
        else:
            sections.append(f"# Organisational context\n{notes}")

    if agent_input.feedback:
        # Feedback is how a failure is routed back upstream (testing -> coding). It is
        # labelled explicitly so the agent addresses it rather than starting over.
        sections.append(
            "# Required corrections\n"
            f"A previous attempt was rejected. Fix specifically this:\n{agent_input.feedback}"
        )

    if agent_input.attempt > 1:
        sections.append(
            f"# Attempt\nThis is attempt {agent_input.attempt}. "
            "Do not repeat an approach that already failed."
        )

    return "\n\n".join(sections)


def _render_payload(payload: dict[str, object]) -> str:
    """Serialise an upstream payload, truncating rather than blowing the context window.

    Truncation is explicit and visible in the prompt: silently dropping fields would
    make a downstream agent confidently reason about data it never received.
    """
    rendered = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if len(rendered) <= MAX_UPSTREAM_CHARS:
        return rendered
    return (
        rendered[:MAX_UPSTREAM_CHARS] + f"\n... [truncated: payload was {len(rendered)} characters]"
    )
