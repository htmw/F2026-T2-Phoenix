"""Generative team design (Level 3).

Given a free-form request, a meta-planner LLM designs a small team of specialist agents
— their roles, what each produces, and who depends on whom — and this module compiles
that design into ephemeral ``AgentDefinition``s and a validated ``WorkflowPlan`` the
existing engine runs unchanged.

Three guardrails make this safe and affordable:

* **Team size is hard-capped** (``max_agents``): a generated plan can never spawn an
  unbounded roster, no matter what the model returns.
* **Every agent is pinned to the cheapest configured model**, so execution stays on the
  cheap tier by construction rather than by hope.
* **Any failure falls back to a fixed default team**, so the feature degrades to a
  working three-agent workflow instead of erroring — the same discipline the capability
  analyser uses.
"""

from __future__ import annotations

import re

from app.core.logging import get_logger
from app.domain.enums import Capability, ModelTrait
from app.providers.base import CompletionRequest, ModelSpec, ProviderError
from app.providers.registry import NoSuitableModelError, ProviderRegistry
from app.schemas.agent import AgentDefinition, AgentLimits, ModelPreference, RetryPolicy
from app.schemas.team import TeamAgentSpec, TeamSpec
from app.schemas.workflow import AgentSelection, WorkflowEdge, WorkflowNode, WorkflowPlan

logger = get_logger(__name__)

# Robust, model-agnostic output shapes. The team is generative in its *roles, wiring, and
# size*; the payload shape stays fixed so validation never depends on the model inventing
# a correct JSON Schema.
_WORKER_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["summary"],
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "details": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
}

_SYNTH_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["document"],
    "properties": {
        "document": {"type": "string"},
        "format": {"type": "string", "enum": ["markdown", "text"]},
        "highlights": {"type": "array", "items": {"type": "string"}},
    },
}

_DESIGN_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["agents"],
    "properties": {
        "domain": {"type": "string"},
        "reasoning": {"type": "string"},
        "agents": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["role", "objective"],
                "properties": {
                    "role": {"type": "string"},
                    "objective": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "is_synthesizer": {"type": "boolean"},
                },
            },
        },
    },
}


class TeamDesigner:
    """Designs a bespoke agent team for a request, with a safe fallback."""

    source = "generative"

    def __init__(self, providers: ProviderRegistry, *, timeout_seconds: float = 30.0) -> None:
        self._providers = providers
        self._timeout = timeout_seconds

    async def design(self, request: str, *, max_agents: int) -> TeamSpec:
        """Return a validated team of at most ``max_agents`` specialists."""
        try:
            provider, model = self._providers.select_model(
                ModelPreference(
                    preferred_traits=(ModelTrait.STRUCTURED_OUTPUT,),
                    min_context_tokens=8_000,
                    temperature=0.2,
                )
            )
        except NoSuitableModelError:
            return _default_team(max_agents)

        completion = CompletionRequest(
            model=model,
            system_prompt=self._system_prompt(max_agents),
            user_prompt=f"Request:\n{request}",
            max_output_tokens=900,
            temperature=0.2,
            response_schema=_DESIGN_SCHEMA,
            timeout_seconds=self._timeout,
        )
        try:
            response = await provider.generate(completion)
        except ProviderError as exc:
            logger.info("team_design_fell_back", reason=f"provider error: {exc.kind.value}")
            return _default_team(max_agents)

        spec = _parse_design(response.text, max_agents)
        if spec is None:
            logger.info("team_design_fell_back", reason="unparseable or empty design")
            return _default_team(max_agents)
        logger.info(
            "team_designed",
            domain=spec.domain,
            agents=[agent.role for agent in spec.agents],
            source=self.source,
        )
        return spec

    @staticmethod
    def _system_prompt(max_agents: int) -> str:
        workers = max_agents - 1
        return (
            "You are a team architect. Design the smallest team of specialist AI agents "
            f"that fully answers the user's request: between 2 and {max_agents} agents "
            "total. Prefer independent specialists that can work in parallel.\n\n"
            f"Rules:\n"
            f"- At most {workers} specialist agents plus EXACTLY ONE synthesizer.\n"
            "- The synthesizer has is_synthesizer=true and depends on the specialists; it "
            "writes the final deliverable.\n"
            "- Each specialist has a distinct role and a concrete objective.\n"
            "- depends_on lists the roles an agent needs results from (usually empty for "
            "specialists).\n\n"
            'Respond with JSON only: {"domain": "...", "reasoning": "...", "agents": '
            '[{"role": "...", "objective": "...", "depends_on": [], '
            '"is_synthesizer": false}]}.'
        )


# ---------------------------------------------------------------------------
# Parsing and validation
# ---------------------------------------------------------------------------


def _parse_design(text: str, max_agents: int) -> TeamSpec | None:
    from app.services.output_validation import extract_json_object

    payload, _, _ = extract_json_object(text)
    if payload is None:
        return None
    raw_agents = payload.get("agents")
    if not isinstance(raw_agents, list) or not raw_agents:
        return None

    specs: list[TeamAgentSpec] = []
    for item in raw_agents:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        objective = str(item.get("objective") or "").strip()
        if not role or not objective:
            continue
        depends = item.get("depends_on")
        depends_on = (
            tuple(str(d).strip() for d in depends if str(d).strip())
            if isinstance(depends, list)
            else ()
        )
        specs.append(
            TeamAgentSpec(
                role=role[:80],
                objective=objective[:2_000],
                depends_on=depends_on,
                is_synthesizer=bool(item.get("is_synthesizer")),
            )
        )

    if not specs:
        return None

    domain = str(payload.get("domain") or "general").strip()[:80] or "general"
    reasoning = str(payload.get("reasoning") or "").strip()[:2_000]
    specs = _normalise(specs, max_agents)
    return TeamSpec(domain=domain, reasoning=reasoning, agents=tuple(specs))


def _normalise(specs: list[TeamAgentSpec], max_agents: int) -> list[TeamAgentSpec]:
    """Enforce the invariants the compiler relies on: exactly one synthesizer, size cap.

    The model is asked for these, but its output is untrusted, so they are imposed here
    rather than assumed.
    """
    synth_indices = [index for index, spec in enumerate(specs) if spec.is_synthesizer]
    # Keep at most one synthesizer; if none was flagged, the last agent becomes it.
    if synth_indices:
        keep = synth_indices[0]
        specs = [
            spec if index == keep else spec.model_copy(update={"is_synthesizer": False})
            for index, spec in enumerate(specs)
        ]
    else:
        specs[-1] = specs[-1].model_copy(update={"is_synthesizer": True})

    workers = [spec for spec in specs if not spec.is_synthesizer]
    synthesizer = next(spec for spec in specs if spec.is_synthesizer)

    # Cap the roster: at most (max_agents - 1) specialists, then the synthesizer.
    workers = workers[: max(1, max_agents - 1)]
    worker_roles = {spec.role for spec in workers}
    # The synthesizer always joins over the workers that survived the cap.
    synthesizer = synthesizer.model_copy(update={"depends_on": tuple(sorted(worker_roles))})
    return [*workers, synthesizer]


def _default_team(max_agents: int) -> TeamSpec:
    """A dependable three-agent team for when generation is unavailable."""
    workers: tuple[TeamAgentSpec, ...] = (
        TeamAgentSpec(
            role="Analyst",
            objective="Break down the request and analyse the core question or problem.",
        ),
        TeamAgentSpec(
            role="Specialist",
            objective="Do the substantive work the request calls for and report concrete results.",
        ),
    )
    workers = workers[: max(1, max_agents - 1)]
    synthesizer = TeamAgentSpec(
        role="Synthesizer",
        objective="Combine the specialists' results into one clear, complete deliverable.",
        depends_on=tuple(sorted(spec.role for spec in workers)),
        is_synthesizer=True,
    )
    logger.info(
        "team_designed",
        domain="general",
        agents=[s.role for s in (*workers, synthesizer)],
        source="default",
    )
    return TeamSpec(
        domain="general",
        reasoning="default team (generation unavailable)",
        agents=(*workers, synthesizer),
    )


# ---------------------------------------------------------------------------
# Compilation: TeamSpec -> ephemeral agents + WorkflowPlan
# ---------------------------------------------------------------------------


def build_team(
    request: str,
    spec: TeamSpec,
    *,
    providers: ProviderRegistry,
    budget_usd: float,
) -> tuple[list[AgentDefinition], WorkflowPlan]:
    """Compile a team design into ephemeral agents and a runnable graph.

    Every agent is pinned to the cheapest configured model and given an equal slice of
    the run budget as its own hard ceiling, so a designed team cannot outspend the cap.
    """
    cheap = _cheapest_model(providers)
    preference_base: dict[str, object] = {"min_context_tokens": 8_000, "max_output_tokens": 4_096}
    if cheap is not None:
        preference_base["preferred_model"] = cheap.id
        preference_base["preferred_provider"] = cheap.provider

    # Equal slice of the run budget per agent, clamped under the AgentLimits ceiling.
    per_agent_cap = round(min(90.0, max(0.02, budget_usd / max(1, len(spec.agents)))), 4)

    # Assign a stable, unique key/id to each role up front so edges can reference them.
    keys: dict[str, str] = {}
    used: set[str] = set()
    for agent in spec.agents:
        key = _unique(_slug(agent.role) or "agent", used)
        used.add(key)
        keys[agent.role] = key

    agents: list[AgentDefinition] = []
    nodes: list[WorkflowNode] = []
    for agent in spec.agents:
        key = keys[agent.role]
        agent_id = f"gen-{key}"[:64]
        is_synth = agent.is_synthesizer
        agents.append(
            AgentDefinition(
                id=agent_id,
                name=agent.role,
                description=agent.objective[:200] or agent.role,
                capabilities=frozenset({Capability.GENERAL_ASSISTANCE}),
                instructions=_instructions(agent, is_synth),
                output_schema=_SYNTH_OUTPUT_SCHEMA if is_synth else _WORKER_OUTPUT_SCHEMA,
                model_preference=ModelPreference(
                    temperature=0.3 if is_synth else 0.2, **preference_base
                ),
                limits=AgentLimits(timeout_seconds=180.0, max_cost_usd=per_agent_cap),
                retry_policy=RetryPolicy(max_attempts=2),
            )
        )
        nodes.append(
            WorkflowNode(
                key=key,
                agent_id=agent_id,
                objective=_objective(request, agent),
                join_policy="any" if is_synth else "all",
            )
        )

    edges = _build_edges(spec, keys)
    plan = _assemble_plan(nodes, edges, spec)
    return agents, plan


def _build_edges(spec: TeamSpec, keys: dict[str, str]) -> list[WorkflowEdge]:
    edges: list[WorkflowEdge] = []
    seen: set[tuple[str, str]] = set()
    for agent in spec.agents:
        target = keys[agent.role]
        for source_role in agent.depends_on:
            source = keys.get(source_role)
            if source is None or source == target:
                continue
            pair = (source, target)
            if pair in seen:
                continue
            seen.add(pair)
            edges.append(WorkflowEdge(source=source, target=target))
    return edges


def _assemble_plan(
    nodes: list[WorkflowNode], edges: list[WorkflowEdge], spec: TeamSpec
) -> WorkflowPlan:
    selection = AgentSelection(
        required_capabilities=(),
        selected=tuple(node.agent_id for node in nodes),
        excluded={},
        reasoning=f"[{spec.domain}] {spec.reasoning}".strip(),
    )
    try:
        return WorkflowPlan(nodes=tuple(nodes), edges=tuple(edges), selection=selection)
    except ValueError:
        # A generated dependency produced a cycle or dangling edge: fall back to a linear
        # chain over the same nodes, which is always a valid DAG.
        logger.info("team_plan_linearised", reason="generated edges were not a valid DAG")
        chain = tuple(
            WorkflowEdge(source=nodes[index - 1].key, target=nodes[index].key)
            for index in range(1, len(nodes))
        )
        return WorkflowPlan(nodes=tuple(nodes), edges=chain, selection=selection)


def _instructions(agent: TeamAgentSpec, is_synth: bool) -> str:
    if is_synth:
        return (
            f"You are the {agent.role} on a specialist team. {agent.objective}\n"
            "Combine the upstream specialists' results into ONE cohesive, complete "
            "deliverable, written in `document` as markdown. Use only what the "
            "specialists actually reported; name any gaps rather than inventing content."
        )
    return (
        f"You are the {agent.role}, one specialist on a coordinated team. {agent.objective}\n"
        "Do only your part and report results your teammates can build on. Put your full "
        "work in `details`, key points in `findings`, and a one-line label in `summary`."
    )


def _objective(request: str, agent: TeamAgentSpec) -> str:
    return (
        f"{request}\n\n"
        f"Your role on the team: {agent.role}. {agent.objective} "
        "Address only your part; other specialists handle the rest."
    )


def _cheapest_model(providers: ProviderRegistry) -> ModelSpec | None:
    models = providers.available_models()
    if not models:
        return None
    return min(models, key=lambda m: (m.output_cost_per_million, m.input_cost_per_million, m.id))


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48]


def _unique(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    index = 2
    while f"{base}-{index}" in used:
        index += 1
    return f"{base}-{index}"
