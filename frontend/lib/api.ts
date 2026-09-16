import type {
  AgentMailbox,
  AgentMessage,
  AgentSummary,
  ArtifactView,
  BackendStatus,
  DecisionView,
  MemoryView,
  MetricsSummary,
  OfficeSnapshot,
  OperatorLimits,
  ProviderActionResult,
  ProviderStatus,
  RoutingPolicy,
  RoutingStrategy,
  WorkflowView,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const OPERATOR_STORAGE_KEY = "agentorch.operatorId";

export function getOperatorId(): string {
  if (typeof window === "undefined") {
    return "operator";
  }
  const stored = window.localStorage.getItem(OPERATOR_STORAGE_KEY);
  return (stored?.trim() || "operator").slice(0, 64);
}

export function setOperatorId(value: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(OPERATOR_STORAGE_KEY, value.trim().slice(0, 64) || "operator");
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Operator-Id": getOperatorId(),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail !== undefined) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      detail = await response.text();
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export async function fetchBackendStatus(): Promise<BackendStatus> {
  try {
    const response = await fetch(`${API_BASE}/readyz`, {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (response.status !== 200 && response.status !== 503) {
      return { reachable: false, error: `Unexpected status ${response.status}` };
    }
    const body = (await response.json()) as { status: string };
    return { reachable: true, status: body.status };
  } catch (error) {
    return {
      reachable: false,
      error: error instanceof Error ? error.message : "Unknown error",
    };
  }
}

export async function getOperatorLimits(): Promise<OperatorLimits> {
  return request<OperatorLimits>("/api/v1/me/limits");
}

export async function listAgents(): Promise<AgentSummary[]> {
  return request<AgentSummary[]>("/api/v1/agents");
}

export async function listProviders(): Promise<ProviderStatus[]> {
  return request<ProviderStatus[]>("/api/v1/providers");
}

export async function connectProvider(
  providerId: string,
  apiKey: string,
): Promise<ProviderActionResult> {
  return request<ProviderActionResult>(`/api/v1/providers/${providerId}/connect`, {
    method: "POST",
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function testProvider(providerId: string): Promise<ProviderActionResult> {
  return request<ProviderActionResult>(`/api/v1/providers/${providerId}/test`, {
    method: "POST",
  });
}

export async function refreshProviderModels(
  providerId: string,
): Promise<ProviderActionResult> {
  return request<ProviderActionResult>(`/api/v1/providers/${providerId}/refresh-models`, {
    method: "POST",
  });
}

export async function disconnectProvider(
  providerId: string,
): Promise<ProviderActionResult> {
  return request<ProviderActionResult>(`/api/v1/providers/${providerId}/disconnect`, {
    method: "DELETE",
  });
}

export async function getRoutingPolicy(): Promise<RoutingPolicy> {
  return request<RoutingPolicy>("/api/v1/providers/routing-policy");
}

export async function updateRoutingPolicy(body: RoutingPolicy): Promise<RoutingPolicy> {
  return request<RoutingPolicy>("/api/v1/providers/routing-policy", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export async function submitTask(body: {
  request: string;
  max_cost_usd: number | null;
  require_approval: boolean;
  agent_ids: string[] | null;
  routing_strategy: RoutingStrategy;
  shared_model: string | null;
  model_overrides: Record<string, string>;
}): Promise<WorkflowView> {
  return request<WorkflowView>("/api/v1/tasks?wait=false", {
    method: "POST",
    body: JSON.stringify({
      request: body.request,
      max_cost_usd: body.max_cost_usd,
      require_approval: body.require_approval,
      agent_ids: body.agent_ids,
      routing_strategy: body.routing_strategy,
      shared_model: body.shared_model,
      model_overrides: body.model_overrides,
    }),
  });
}

export async function setAgentModelBinding(
  agentId: string,
  preferredModel: string | null,
): Promise<AgentSummary> {
  return request<AgentSummary>(`/api/v1/agents/${encodeURIComponent(agentId)}/model-binding`, {
    method: "PATCH",
    body: JSON.stringify({ preferred_model: preferredModel }),
  });
}

export async function listWorkflows(limit = 50): Promise<WorkflowView[]> {
  return request<WorkflowView[]>(`/api/v1/workflows?limit=${limit}`);
}

export async function getWorkflow(id: string): Promise<WorkflowView> {
  return request<WorkflowView>(`/api/v1/workflows/${id}`);
}

export async function cancelWorkflow(id: string): Promise<WorkflowView> {
  return request<WorkflowView>(`/api/v1/workflows/${id}/cancel`, { method: "POST" });
}

export async function controlNode(
  workflowId: string,
  nodeKey: string,
  action: "approve" | "reject" | "retry" | "skip",
  decision?: { reason?: string | null },
): Promise<WorkflowView> {
  return request<WorkflowView>(
    `/api/v1/workflows/${workflowId}/nodes/${nodeKey}/${action}?wait=false`,
    {
      method: "POST",
      body: JSON.stringify(decision ?? {}),
    },
  );
}

export async function getOffice(): Promise<OfficeSnapshot> {
  return request<OfficeSnapshot>("/api/v1/office");
}

export async function getInbox(agentId: string): Promise<AgentMessage[]> {
  return request<AgentMessage[]>(`/api/v1/messages?inbox=${encodeURIComponent(agentId)}`);
}

export async function getMailbox(agentId: string): Promise<AgentMailbox> {
  return request<AgentMailbox>(`/api/v1/agents/${encodeURIComponent(agentId)}/mailbox`);
}

export async function getMessage(messageId: string): Promise<AgentMessage> {
  return request<AgentMessage>(`/api/v1/messages/${encodeURIComponent(messageId)}`);
}

export async function getMemory(agentId: string): Promise<MemoryView[]> {
  return request<MemoryView[]>(`/api/v1/memory?agent_id=${encodeURIComponent(agentId)}`);
}

export async function listArtifacts(params?: {
  created_by?: string;
  workflow_id?: string;
  limit?: number;
}): Promise<ArtifactView[]> {
  const query = new URLSearchParams();
  if (params?.created_by) {
    query.set("created_by", params.created_by);
  }
  if (params?.workflow_id) {
    query.set("workflow_id", params.workflow_id);
  }
  if (params?.limit != null) {
    query.set("limit", String(params.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<ArtifactView[]>(`/api/v1/artifacts${suffix}`);
}

export async function getArtifact(artifactId: string): Promise<ArtifactView> {
  return request<ArtifactView>(`/api/v1/artifacts/${encodeURIComponent(artifactId)}`);
}

export async function listDecisions(params?: {
  agent_id?: string;
  workflow_id?: string;
  kind?: string;
  limit?: number;
}): Promise<DecisionView[]> {
  const query = new URLSearchParams();
  if (params?.agent_id) {
    query.set("agent_id", params.agent_id);
  }
  if (params?.workflow_id) {
    query.set("workflow_id", params.workflow_id);
  }
  if (params?.kind) {
    query.set("kind", params.kind);
  }
  if (params?.limit != null) {
    query.set("limit", String(params.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<DecisionView[]>(`/api/v1/decisions${suffix}`);
}

export async function getMetrics(): Promise<MetricsSummary> {
  return request<MetricsSummary>("/api/v1/metrics");
}

export { API_BASE };
