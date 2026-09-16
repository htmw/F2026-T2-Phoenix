"""Deciding which capabilities a request needs.

This is the platform's central judgement: too few capabilities and the request is
half-answered, too many and the user pays for agents that had nothing to do.

Two strategies implement the same protocol. The heuristic one is deterministic, free,
and always available; the LLM-backed one handles phrasing the heuristic cannot and falls
back to it on any failure. Neither strategy names agents — both return capabilities,
which selection then resolves against the registry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from app.core.logging import get_logger
from app.domain.enums import Capability
from app.providers.base import CompletionRequest, ProviderError
from app.providers.registry import NoSuitableModelError, ProviderRegistry
from app.schemas.agent import ModelPreference

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CapabilityAnalysis:
    required: frozenset[Capability]
    reasoning: str
    #: Which strategy produced this, so a surprising plan can be traced to its source.
    source: str
    #: Capabilities considered and rejected, with the reason.
    rejected: dict[Capability, str] = field(default_factory=dict)


class CapabilityAnalyser(Protocol):
    async def analyse(self, request: str) -> CapabilityAnalysis: ...


# ---------------------------------------------------------------------------
# Heuristic analysis
# ---------------------------------------------------------------------------

# Keyword groups per capability. Deliberately narrow: a false positive costs the user a
# wasted agent, so a phrase earns a capability only when it clearly implies the work.
_SIGNALS: dict[Capability, tuple[str, ...]] = {
    Capability.VULNERABILITY_ANALYSIS: (
        "security",
        "vulnerab",
        "exploit",
        "injection",
        "xss",
        "csrf",
        "insecure",
        "audit",
        "penetration",
        "cve",
        "hardcoded credential",
        "secret leak",
    ),
    Capability.DEPENDENCY_AUDIT: ("dependenc", "package", "supply chain", "outdated librar"),
    Capability.CODE_GENERATION: (
        "write code",
        "implement",
        "build a",
        "create a function",
        "generate code",
        "add a feature",
        "scaffold",
    ),
    Capability.CODE_MODIFICATION: (
        "fix",
        "refactor",
        "patch",
        "modify",
        "update the code",
        "remediate",
        "clean up",
    ),
    Capability.DEBUGGING: ("debug", "why does", "stack trace", "crash", "not working", "error"),
    Capability.TEST_GENERATION: ("test", "unit test", "coverage", "spec for"),
    Capability.TEST_ANALYSIS: ("failing test", "test failure", "flaky"),
    Capability.WEB_RESEARCH: (
        "research",
        "find out",
        "look up",
        "investigate",
        "compare",
        "what is the latest",
        "best practice",
    ),
    Capability.SUMMARISATION: ("summar", "tl;dr", "brief overview", "condense"),
    Capability.CODE_REVIEW: ("review", "code quality", "critique", "assess the code"),
    Capability.DOCUMENTATION: ("document", "readme", "docstring", "api docs", "changelog"),
    Capability.REPORT_GENERATION: ("report", "write up", "summary document", "findings document"),
}

# Requests mentioning several distinct areas need decomposition; a single-area request
# does not, and adding a planning step to it is pure overhead.
_DECOMPOSITION_THRESHOLD = 3

_MULTI_STEP_PHRASES = (
    "and then",
    "after that",
    "step by step",
    "end to end",
    "full workflow",
    "everything",
)


class HeuristicCapabilityAnalyser:
    """Keyword-driven analysis.

    Free, instant, and deterministic, which makes it the right default and the right
    fallback. Its weakness is phrasing that implies work without using its vocabulary —
    exactly what the LLM analyser is for.
    """

    source = "heuristic"

    async def analyse(self, request: str) -> CapabilityAnalysis:
        lowered = request.lower()
        required: set[Capability] = set()
        rejected: dict[Capability, str] = {}
        matched_terms: dict[Capability, str] = {}

        for capability, signals in _SIGNALS.items():
            hit = next((signal for signal in signals if signal in lowered), None)
            if hit:
                required.add(capability)
                matched_terms[capability] = hit
            else:
                rejected[capability] = "no signal for this capability in the request"

        if not required:
            # Unclassified briefs go to the General desk — not Research — so the office
            # does not invent a research workflow for open-ended asks.
            required.add(Capability.GENERAL_ASSISTANCE)
            rejected.pop(Capability.GENERAL_ASSISTANCE, None)
            matched_terms[Capability.GENERAL_ASSISTANCE] = "(default for an unclassified request)"

        wants_decomposition = len(required) >= _DECOMPOSITION_THRESHOLD or any(
            phrase in lowered for phrase in _MULTI_STEP_PHRASES
        )
        if wants_decomposition:
            required.add(Capability.TASK_DECOMPOSITION)
            rejected.pop(Capability.TASK_DECOMPOSITION, None)
        else:
            rejected[Capability.TASK_DECOMPOSITION] = (
                "request is narrow enough not to need planning"
            )

        # Fixing code implies producing code, and reviewing changes implies there are
        # changes to review; these implications avoid a half-built result.
        if Capability.CODE_MODIFICATION in required and Capability.DEBUGGING in required:
            rejected.pop(Capability.CODE_GENERATION, None)

        reasoning = self._explain(matched_terms, wants_decomposition)
        return CapabilityAnalysis(
            required=frozenset(required),
            reasoning=reasoning,
            source=self.source,
            rejected=rejected,
        )

    @staticmethod
    def _explain(matched: dict[Capability, str], decomposed: bool) -> str:
        parts = [
            f"'{term}' implies {capability.value}"
            for capability, term in sorted(matched.items(), key=lambda item: item[0].value)
        ]
        if decomposed:
            parts.append("request spans several areas, so planning was added")
        return "; ".join(parts)


# ---------------------------------------------------------------------------
# LLM-backed analysis
# ---------------------------------------------------------------------------


_ANALYSIS_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["capabilities"],
    "properties": {
        "capabilities": {"type": "array", "items": {"type": "string"}},
        "reasoning": {"type": "string"},
    },
}


class LLMCapabilityAnalyser:
    """Analysis by a model, constrained to the known capability vocabulary.

    The model is given the exact list of capabilities and may only choose from it, so a
    hallucinated capability is dropped rather than propagated. Any failure — provider
    down, malformed output, nothing recognised — falls back to the heuristic analyser,
    because a request must still be answerable when the planning model is unavailable.
    """

    source = "llm"

    def __init__(
        self,
        providers: ProviderRegistry,
        fallback: CapabilityAnalyser | None = None,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._providers = providers
        self._fallback = fallback or HeuristicCapabilityAnalyser()
        self._timeout = timeout_seconds

    async def analyse(self, request: str) -> CapabilityAnalysis:
        try:
            provider, model = self._providers.select_model(
                ModelPreference(min_context_tokens=8_000, temperature=0.0)
            )
        except NoSuitableModelError:
            return await self._fall_back(request, "no model available for analysis")

        completion = CompletionRequest(
            model=model,
            system_prompt=self._system_prompt(),
            user_prompt=f"Request:\n{request}",
            max_output_tokens=800,
            temperature=0.0,
            response_schema=_ANALYSIS_SCHEMA,
            timeout_seconds=self._timeout,
        )

        try:
            response = await provider.generate(completion)
        except ProviderError as exc:
            return await self._fall_back(request, f"provider error: {exc.kind.value}")

        recognised, unknown = self._parse(response.text)
        if not recognised:
            return await self._fall_back(request, "model named no known capability")

        if unknown:
            # Visible rather than silent: a model repeatedly inventing capabilities is a
            # signal the prompt or the vocabulary needs work.
            logger.warning("analysis_named_unknown_capabilities", unknown=sorted(unknown))

        rejected = {
            capability: "not selected by analysis"
            for capability in Capability
            if capability not in recognised
        }
        return CapabilityAnalysis(
            required=frozenset(recognised),
            reasoning=self._reasoning(response.text) or "selected by model analysis",
            source=self.source,
            rejected=rejected,
        )

    async def _fall_back(self, request: str, reason: str) -> CapabilityAnalysis:
        logger.info("capability_analysis_fell_back", reason=reason)
        analysis = await self._fallback.analyse(request)
        return CapabilityAnalysis(
            required=analysis.required,
            reasoning=f"{analysis.reasoning} (fell back: {reason})",
            source=f"{self.source}->fallback",
            rejected=analysis.rejected,
        )

    @staticmethod
    def _system_prompt() -> str:
        vocabulary = "\n".join(f"- {capability.value}" for capability in Capability)
        return (
            "You decide which capabilities a request requires. Choose the smallest set "
            "that fully satisfies it: every capability you name causes an AI agent to "
            "run, which costs the user time and money.\n\n"
            f"Choose only from this list:\n{vocabulary}\n\n"
            'Respond with JSON: {"capabilities": ["..."], "reasoning": "..."}. '
            "Do not invent capabilities that are not listed."
        )

    @staticmethod
    def _parse(text: str) -> tuple[set[Capability], set[str]]:
        from app.services.output_validation import extract_json_object

        payload, _, _ = extract_json_object(text)
        if payload is None:
            return set(), set()

        listed = payload.get("capabilities")
        if not isinstance(listed, list):
            return set(), set()

        known = {capability.value: capability for capability in Capability}
        recognised: set[Capability] = set()
        unknown: set[str] = set()
        for item in listed:
            name = str(item).strip()
            if name in known:
                recognised.add(known[name])
            else:
                unknown.add(name)
        return recognised, unknown

    @staticmethod
    def _reasoning(text: str) -> str | None:
        try:
            payload = json.loads(re.sub(r"^```(?:json)?|```$", "", text.strip()))
        except ValueError:
            return None
        reasoning = payload.get("reasoning") if isinstance(payload, dict) else None
        return str(reasoning)[:1_000] if isinstance(reasoning, str) else None
