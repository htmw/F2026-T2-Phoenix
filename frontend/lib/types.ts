export type NodeStatus =
  | "waiting"
  | "ready"
  | "running"
  | "completed"
  | "skipped"
  | "failed"
  | "cancelled"
  | "awaiting_approval";

export type WorkflowStatus =
  | "pending"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "cancelled";

export type ExecutionSummary = {
  attempt: number;
  status: string;
  provider: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  error_kind: string | null;
  error_message: string | null;
};

export type ApprovalView = {
  approved: boolean;
  decided_by: string;
  reason: string | null;
  decided_at: string | null;
};

export type NodeView = {
  key: string;
  agent_id: string;
  agent_name: string;
  objective: string;
  status: NodeStatus;
  satisfies: string[];
  requires_approval: boolean;
  skip_reason: string | null;
  join_policy: string;
  feedback_target: string | null;
  attempts: number;
  result: Record<string, unknown>;
  executions: ExecutionSummary[];
  approval: ApprovalView | null;
};

export type EdgeView = {
  source: string;
  target: string;
  condition: Record<string, unknown> | null;
};

export type WorkflowView = {
  id: string;
  task_id: string;
  status: WorkflowStatus;
  request: string;
  owner_id?: string;
  parent_workflow_id?: string | null;
  nodes: NodeView[];
  edges: EdgeView[];
  selection: Record<string, unknown>;
  total_cost_usd: number;
  final_result: Record<string, unknown>;
  error: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type BackendStatus =
  | { reachable: true; status: string }
  | { reachable: false; error: string };

export const TERMINAL_STATUSES: ReadonlySet<WorkflowStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
]);

export type AgentRuntimeStatus =
  | "online"
  | "idle"
  | "thinking"
  | "working"
  | "waiting"
  | "blocked"
  | "failed"
  | "offline";

export type OperatorLimits = {
  operator_id: string;
  rate_limit: number;
  rate_remaining: number;
  rate_reset_at: number;
  budget_cap_usd: number | null;
  budget_spent_usd: number;
  budget_window_hours: number;
};

export type AgentSummary = {
  id: string;
  name: string;
  description: string;
  capabilities: string[];
  tools: string[];
  model_strategy: "auto" | "fixed";
  preferred_provider: string | null;
  preferred_model: string | null;
  enabled: boolean;
};

export type ModelView = {
  id: string;
  provider: string;
  traits: string[];
  context_tokens: number;
  max_output_tokens: number;
  input_cost_per_million: number;
  output_cost_per_million: number;
  demo: boolean;
  verified?: boolean;
};

export type ProviderStatus = {
  name: string;
  label: string;
  configured: boolean;
  demo: boolean;
  auth_method?: string;
  access_label?: string;
  connection_status?: string;
  credential_source?: string;
  key_hint?: string | null;
  last_verified_at?: string | null;
  last_error?: string | null;
  discovered_models?: string[];
  models: ModelView[];
};

export type ProviderActionResult = {
  provider: ProviderStatus;
  message: string;
};

export type RoutingPolicy = {
  provider_priority: string[];
  blocked_models: string[];
};

export type RoutingStrategy = "auto" | "one" | "mixed";

export type PresenceView = {
  agent_id: string;
  status: AgentRuntimeStatus;
  current_task: string | null;
  waiting_for: string | null;
  sending_to: string | null;
  detail: string | null;
};

export type AgentOfficeView = {
  agent: AgentSummary;
  presence: PresenceView;
  inbox_unread: number;
};

export type NetworkLink = {
  source: string;
  target: string;
  type: string;
  count: number;
  last_at: string;
};

export type AgentMessage = {
  id: string;
  sender: string;
  recipient: string | null;
  type: string;
  priority: string;
  status: string;
  workflow_id: string | null;
  task_id: string | null;
  node_key: string | null;
  parent_id: string | null;
  content: Record<string, unknown>;
  artifact_ids: string[];
  requires_response: boolean;
  created_at: string;
  acknowledged_at: string | null;
  completed_at: string | null;
};

export type AgentMailbox = {
  inbox: AgentMessage[];
  sent: AgentMessage[];
  archive: AgentMessage[];
};

export type NetworkEvent = {
  id: string;
  event_type: string;
  actor_id: string | null;
  workflow_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
};

export type MemoryView = {
  id: string;
  visibility: "private" | "shared" | "workflow";
  title: string;
  owner_agent_id: string | null;
  source_agent_id: string | null;
  tags: string[];
  created_at: string;
};

export type ArtifactView = {
  id: string;
  kind: string;
  created_by: string;
  uri: string;
  title: string;
  workflow_id: string | null;
  content_type: string | null;
  extra: Record<string, unknown>;
  size_bytes: number;
  created_at: string;
};

export type DecisionView = {
  id: string;
  kind: string;
  actor_id: string;
  agent_id: string | null;
  workflow_id: string | null;
  node_key: string | null;
  title: string;
  summary: string | null;
  payload: Record<string, unknown>;
  tags: string[];
  importance: number;
  expires_at: string | null;
  created_at: string;
};

export type OfficeSnapshot = {
  agents: AgentOfficeView[];
  links: NetworkLink[];
  recent_messages: AgentMessage[];
  recent_events: NetworkEvent[];
};

export type MetricsSummary = {
  workflow_count: number;
  attempt_count: number;
  total_cost_usd: number;
  token_totals: { input: number; output: number; total: number };
  slowest_agent: { agent_id: string; latency_ms: number } | null;
  retry_counts: Record<string, number>;
  failing_providers: Record<string, number>;
};
