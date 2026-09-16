"""Built-in agent definitions.

These are *seed data*, not special cases. The orchestrator and executor read the
registry, not this module, so an operator can add, disable, or replace an agent by
changing rows instead of engine code. Display-name helpers are the one exception the
API uses so the graph shows "Security Agent" rather than a stripped id.

Capability sets are deliberately disjoint where the domains are distinct: overlapping
declarations would make selection ambiguous and risk activating two agents for one need.

Agents declare *traits*, not vendor model ids. Any connected compatible model can power
any agent; Fixed bindings are optional operator overrides, never part of the role.
"""

from __future__ import annotations

from app.domain.enums import Capability, ModelTrait
from app.schemas.agent import AgentDefinition, AgentLimits, ModelPreference, RetryPolicy

# Reusable JSON Schema fragments. Every output schema is an object so downstream input
# can be built from named fields.
_STRING_ARRAY = {"type": "array", "items": {"type": "string"}}


PLANNING_AGENT = AgentDefinition(
    id="planning-agent",
    name="Planning Agent",
    description=(
        "Decomposes a complex request into discrete steps and identifies the "
        "capabilities each step requires."
    ),
    capabilities=frozenset({Capability.TASK_DECOMPOSITION}),
    instructions=(
        "You are a planning agent. Break the user's request into the smallest set of "
        "concrete steps that satisfies it. For each step, state the single capability "
        "it requires. Do not invent work the request does not ask for. If one step is "
        "enough, return one step."
    ),
    output_schema={
        "type": "object",
        "required": ["steps"],
        "additionalProperties": False,
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["description", "capability"],
                    "properties": {
                        "description": {"type": "string"},
                        "capability": {"type": "string"},
                        "depends_on": _STRING_ARRAY,
                    },
                },
            },
            "rationale": {"type": "string"},
        },
    },
    model_preference=ModelPreference(
        required_traits=(ModelTrait.REASONING,),
        preferred_traits=(ModelTrait.STRUCTURED_OUTPUT,),
        temperature=0.1,
    ),
    limits=AgentLimits(timeout_seconds=90.0, max_cost_usd=0.25),
)


RESEARCH_AGENT = AgentDefinition(
    id="research-agent",
    name="Research Agent",
    description="Gathers external information, summarises it, and extracts sources.",
    capabilities=frozenset(
        {
            Capability.WEB_RESEARCH,
            Capability.SUMMARISATION,
            Capability.SOURCE_EXTRACTION,
        }
    ),
    instructions=(
        "You are a research agent. Answer the objective using the supplied material "
        "and your knowledge. Separate established facts from inference, and attribute "
        "every claim you can. State explicitly what you could not determine."
    ),
    output_schema={
        "type": "object",
        "required": ["findings"],
        "properties": {
            "findings": {"type": "array", "items": {"type": "string"}},
            "summary": {"type": "string"},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "reliability": {"type": "string"},
                    },
                },
            },
            "unresolved": _STRING_ARRAY,
        },
    },
    model_preference=ModelPreference(
        preferred_traits=(ModelTrait.LONG_CONTEXT, ModelTrait.FAST),
        min_context_tokens=32_000,
    ),
    tools=("web_search",),
    permissions=("network:read",),
    limits=AgentLimits(timeout_seconds=180.0, max_cost_usd=0.40),
)


SECURITY_AGENT = AgentDefinition(
    id="security-agent",
    name="Security Agent",
    description=("Analyses code and dependencies for vulnerabilities and recommends remediation."),
    capabilities=frozenset(
        {
            Capability.VULNERABILITY_ANALYSIS,
            Capability.SECURITY_RECOMMENDATION,
            Capability.DEPENDENCY_AUDIT,
        }
    ),
    instructions=(
        "You are a security analysis agent. Report only vulnerabilities you can point "
        "to in the supplied material. For each, give severity, location, the issue, and "
        "a concrete remediation. If you find nothing, return an empty findings list — "
        "an empty result is a valid and useful answer, and inventing issues is worse "
        "than finding none."
    ),
    output_schema={
        "type": "object",
        "required": ["findings"],
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["severity", "issue"],
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "high", "medium", "low", "info"],
                        },
                        "file": {"type": "string"},
                        "line": {"type": "integer"},
                        "issue": {"type": "string"},
                        "recommendation": {"type": "string"},
                        "cwe": {"type": "string"},
                    },
                },
            },
            "summary": {"type": "string"},
            "scanned": _STRING_ARRAY,
        },
    },
    model_preference=ModelPreference(
        required_traits=(ModelTrait.REASONING,),
        preferred_traits=(ModelTrait.CODING,),
        temperature=0.0,
    ),
    permissions=("repo:read",),
    limits=AgentLimits(timeout_seconds=240.0, max_cost_usd=0.75),
)


CODING_AGENT = AgentDefinition(
    id="coding-agent",
    name="Coding Agent",
    description="Writes, modifies, and debugs code in response to a concrete objective.",
    capabilities=frozenset(
        {
            Capability.CODE_GENERATION,
            Capability.CODE_MODIFICATION,
            Capability.DEBUGGING,
        }
    ),
    instructions=(
        "You are a coding agent. Make the smallest change that satisfies the objective. "
        "Return complete file contents or precise diffs, never a sketch. If upstream "
        "feedback describes a test failure, fix that specific failure rather than "
        "rewriting unrelated code."
    ),
    output_schema={
        "type": "object",
        "required": ["changes"],
        "properties": {
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["file", "action"],
                    "properties": {
                        "file": {"type": "string"},
                        "action": {
                            "type": "string",
                            "enum": ["create", "modify", "delete"],
                        },
                        "content": {"type": "string"},
                        "diff": {"type": "string"},
                        "explanation": {"type": "string"},
                    },
                },
            },
            "summary": {"type": "string"},
            "follow_ups": _STRING_ARRAY,
        },
    },
    model_preference=ModelPreference(
        required_traits=(ModelTrait.CODING,),
        preferred_traits=(ModelTrait.REASONING,),
        min_context_tokens=64_000,
        max_output_tokens=16_384,
        temperature=0.1,
    ),
    permissions=("repo:read", "repo:write"),
    limits=AgentLimits(timeout_seconds=300.0, max_cost_usd=1.50),
    retry_policy=RetryPolicy(max_attempts=3, initial_backoff_seconds=2.0),
)


TESTING_AGENT = AgentDefinition(
    id="testing-agent",
    name="Testing Agent",
    description="Generates tests, analyses failures, and reports test outcomes.",
    capabilities=frozenset(
        {
            Capability.TEST_GENERATION,
            Capability.TEST_ANALYSIS,
            Capability.TEST_EXECUTION,
        }
    ),
    instructions=(
        "You are a testing agent. Write tests that would fail without the change under "
        "test, covering at least one failure path. When analysing failures, identify the "
        "root cause and say which file must change — that message is routed back to the "
        "coding agent, so be specific."
    ),
    output_schema={
        "type": "object",
        "required": ["passed"],
        "properties": {
            "passed": {"type": "boolean"},
            "tests": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "file": {"type": "string"},
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["passed", "failed", "skipped", "generated"],
                        },
                    },
                },
            },
            "failures": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "test": {"type": "string"},
                        "message": {"type": "string"},
                        "suspected_file": {"type": "string"},
                    },
                },
            },
            "summary": {"type": "string"},
        },
    },
    model_preference=ModelPreference(
        required_traits=(ModelTrait.CODING,),
        temperature=0.1,
        max_output_tokens=8_192,
    ),
    permissions=("repo:read", "repo:write", "process:execute"),
    limits=AgentLimits(timeout_seconds=300.0, max_cost_usd=0.90),
    retry_policy=RetryPolicy(max_attempts=2),
)


REVIEW_AGENT = AgentDefinition(
    id="review-agent",
    name="Review Agent",
    description="Reviews work produced by other agents and assesses whether it is acceptable.",
    capabilities=frozenset({Capability.CODE_REVIEW, Capability.QUALITY_ASSESSMENT}),
    instructions=(
        "You are a review agent. Judge the upstream work against the original "
        "objective. Report concrete defects with their location and severity. Approve "
        "only if the objective is met; say plainly what is missing when it is not."
    ),
    output_schema={
        "type": "object",
        "required": ["approved"],
        "properties": {
            "approved": {"type": "boolean"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["severity", "description"],
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["blocker", "major", "minor", "nit"],
                        },
                        "file": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "assessment": {"type": "string"},
        },
    },
    model_preference=ModelPreference(
        required_traits=(ModelTrait.REASONING,),
        preferred_traits=(ModelTrait.CODING,),
        temperature=0.0,
    ),
    limits=AgentLimits(timeout_seconds=180.0, max_cost_usd=0.80),
)


DOCUMENTATION_AGENT = AgentDefinition(
    id="documentation-agent",
    name="Documentation Agent",
    description="Writes documentation and assembles reports from upstream agent results.",
    capabilities=frozenset({Capability.DOCUMENTATION, Capability.REPORT_GENERATION}),
    instructions=(
        "You are a documentation agent. Write for a reader who did not watch the work "
        "happen. Use only what upstream agents actually reported; if something was not "
        "done or was skipped, say so rather than omitting it."
    ),
    output_schema={
        "type": "object",
        "required": ["document"],
        "properties": {
            "document": {"type": "string"},
            "format": {"type": "string", "enum": ["markdown", "text", "html"]},
            "sections": _STRING_ARRAY,
            "omissions": _STRING_ARRAY,
        },
    },
    model_preference=ModelPreference(
        preferred_traits=(ModelTrait.FAST, ModelTrait.LONG_CONTEXT),
        min_context_tokens=32_000,
        max_output_tokens=8_192,
        temperature=0.3,
    ),
    limits=AgentLimits(timeout_seconds=180.0, max_cost_usd=0.40),
)


GENERAL_AGENT = AgentDefinition(
    id="general-agent",
    name="General Agent",
    description=(
        "Handles arbitrary tasks that do not require a specialised desk — coding, "
        "research, writing, planning, debugging, or analysis in one place."
    ),
    capabilities=frozenset({Capability.GENERAL_ASSISTANCE}),
    instructions=(
        "You are a general-purpose agent. Complete the objective directly and "
        "thoroughly. Put the full deliverable the user asked for in the `answer` "
        "field (complete code, prose, analysis — not a teaser). Use `summary` only "
        "as a one-line label. Prefer clear structured output. If the work clearly "
        "needs a specialist later, say so in follow_ups rather than inventing "
        "specialised artifacts you cannot verify."
    ),
    output_schema={
        "type": "object",
        "required": ["summary", "answer"],
        "properties": {
            "summary": {"type": "string"},
            "answer": {"type": "string"},
            "findings": {"type": "array", "items": {"type": "string"}},
            "recommendations": _STRING_ARRAY,
            "follow_ups": _STRING_ARRAY,
            "artifacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "kind": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
            },
        },
    },
    model_preference=ModelPreference(
        preferred_traits=(ModelTrait.REASONING, ModelTrait.STRUCTURED_OUTPUT),
        temperature=0.2,
    ),
    limits=AgentLimits(timeout_seconds=240.0, max_cost_usd=0.75),
)


BUILTIN_AGENTS: tuple[AgentDefinition, ...] = (
    PLANNING_AGENT,
    RESEARCH_AGENT,
    SECURITY_AGENT,
    CODING_AGENT,
    TESTING_AGENT,
    REVIEW_AGENT,
    DOCUMENTATION_AGENT,
    GENERAL_AGENT,
)

BUILTIN_NAMES: dict[str, str] = {agent.id: agent.name for agent in BUILTIN_AGENTS}


def agent_display_name(agent_id: str) -> str:
    """Original display name for a built-in id; title-case fallback for others."""
    known = BUILTIN_NAMES.get(agent_id)
    if known is not None:
        return known
    if agent_id.endswith("-agent"):
        stem = agent_id.removesuffix("-agent").replace("-", " ").title()
        return f"{stem} Agent"
    return agent_id
