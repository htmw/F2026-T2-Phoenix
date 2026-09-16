"""Process-local counters for Prometheus scrapes.

Durable answers to "what did this cost" live in Postgres. These counters exist so a
scrape of this process is cheap and does not contend with reporting queries. A restart
resets them; that is expected of a gauge scraped over time.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock


class ProcessMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.executions_total: dict[tuple[str, str], int] = defaultdict(int)
        self.cost_usd_total = 0.0
        self.input_tokens_total = 0
        self.output_tokens_total = 0
        self.retries_total = 0
        self.provider_failures_total: dict[str, int] = defaultdict(int)

    def observe(
        self,
        *,
        status: str,
        provider: str | None,
        cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        attempt: int,
        error_kind: str | None,
    ) -> None:
        vendor = provider or "unknown"
        with self._lock:
            self.executions_total[(status, vendor)] += 1
            self.cost_usd_total += cost_usd
            self.input_tokens_total += input_tokens
            self.output_tokens_total += output_tokens
            if attempt > 1:
                self.retries_total += 1
            if error_kind:
                self.provider_failures_total[vendor] += 1

    def render_prometheus(self) -> str:
        lines = [
            "# HELP agentorch_executions_total Agent execution attempts.",
            "# TYPE agentorch_executions_total counter",
        ]
        with self._lock:
            for (status, provider), count in sorted(self.executions_total.items()):
                lines.append(
                    f'agentorch_executions_total{{status="{_escape(status)}",'
                    f'provider="{_escape(provider)}"}} {count}'
                )
            lines.extend(
                [
                    "# HELP agentorch_cost_usd_total Estimated spend in this process.",
                    "# TYPE agentorch_cost_usd_total counter",
                    f"agentorch_cost_usd_total {self.cost_usd_total:.8f}",
                    "# HELP agentorch_input_tokens_total Prompt tokens in this process.",
                    "# TYPE agentorch_input_tokens_total counter",
                    f"agentorch_input_tokens_total {self.input_tokens_total}",
                    "# HELP agentorch_output_tokens_total Completion tokens in this process.",
                    "# TYPE agentorch_output_tokens_total counter",
                    f"agentorch_output_tokens_total {self.output_tokens_total}",
                    "# HELP agentorch_retries_total Execution attempts after the first.",
                    "# TYPE agentorch_retries_total counter",
                    f"agentorch_retries_total {self.retries_total}",
                    "# HELP agentorch_provider_failures_total Failed attempts by provider.",
                    "# TYPE agentorch_provider_failures_total counter",
                ]
            )
            for provider, count in sorted(self.provider_failures_total.items()):
                lines.append(
                    f'agentorch_provider_failures_total{{provider="{_escape(provider)}"}} {count}'
                )
        return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


process_metrics = ProcessMetrics()
