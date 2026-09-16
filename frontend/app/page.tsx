"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { AgentDrawer } from "@/components/AgentDrawer";
import { AgentStrip } from "@/components/AgentStrip";
import { AppShell, type NavTab } from "@/components/AppShell";
import { ChatThread } from "@/components/ChatThread";
import { ConversationSidebar } from "@/components/ConversationSidebar";
import { MessagesPanel } from "@/components/MessagesPanel";
import { SettingsPanel } from "@/components/SettingsPanel";
import { TaskComposer } from "@/components/TaskComposer";
import { WorkflowProgress } from "@/components/WorkflowProgress";
import {
  ApiError,
  cancelWorkflow,
  connectProvider,
  controlNode,
  disconnectProvider,
  getMailbox,
  getMemory,
  getOffice,
  getOperatorId,
  getOperatorLimits,
  getRoutingPolicy,
  getWorkflow,
  listAgents,
  listArtifacts,
  listProviders,
  listWorkflows,
  refreshProviderModels,
  setAgentModelBinding,
  setOperatorId,
  submitTask,
  testProvider,
  updateRoutingPolicy,
} from "@/lib/api";
import {
  demoOnly,
  getFreeOnly,
  hasUsableModels,
  liveModels,
  setFreeOnly,
} from "@/lib/office";
import type {
  AgentMailbox,
  AgentSummary,
  ArtifactView,
  MemoryView,
  OfficeSnapshot,
  OperatorLimits,
  ProviderStatus,
  RoutingPolicy,
  RoutingStrategy,
  WorkflowView,
} from "@/lib/types";
import { TERMINAL_STATUSES } from "@/lib/types";

type MailFolder = "inbox" | "sent" | "archive";

export default function HomePage() {
  const [tab, setTab] = useState<NavTab>("home");
  const [office, setOffice] = useState<OfficeSnapshot | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [mailbox, setMailbox] = useState<AgentMailbox | null>(null);
  const [mailFolder, setMailFolder] = useState<MailFolder>("inbox");
  const [memory, setMemory] = useState<MemoryView[]>([]);
  const [deskArtifacts, setDeskArtifacts] = useState<ArtifactView[]>([]);
  const [request, setRequest] = useState("");
  const [requireApproval, setRequireApproval] = useState(false);
  const [maxCost, setMaxCost] = useState("");
  const [actor, setActor] = useState("operator");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowView | null>(null);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [pickAgents, setPickAgents] = useState(false);
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [routingStrategy, setRoutingStrategy] = useState<RoutingStrategy>("auto");
  const [sharedModel, setSharedModel] = useState("");
  const [modelOverrides, setModelOverrides] = useState<Record<string, string>>({});
  const [bindingBusy, setBindingBusy] = useState<string | null>(null);
  const [routingPolicy, setRoutingPolicy] = useState<RoutingPolicy>({
    provider_priority: [],
    blocked_models: [],
  });
  const [policyBusy, setPolicyBusy] = useState(false);
  const [providerKeys, setProviderKeys] = useState<Record<string, string>>({});
  const [providerBusy, setProviderBusy] = useState<string | null>(null);
  const [providerMessage, setProviderMessage] = useState<string | null>(null);
  const [limits, setLimits] = useState<OperatorLimits | null>(null);
  const [freeOnly, setFreeOnlyState] = useState(true);
  const [advancedComposer, setAdvancedComposer] = useState(false);
  const [advancedSettings, setAdvancedSettings] = useState(false);
  const [advancedWorkflow, setAdvancedWorkflow] = useState(false);
  const [advancedDrawer, setAdvancedDrawer] = useState(false);
  const [showMsgDev, setShowMsgDev] = useState(false);
  const [conversations, setConversations] = useState<WorkflowView[]>([]);
  const [composerMode, setComposerMode] = useState<"new" | "followup">("new");


  useEffect(() => {
    setActor(getOperatorId());
    setFreeOnlyState(getFreeOnly());
  }, []);

  const refreshLimits = useCallback(async () => {
    try {
      setLimits(await getOperatorLimits());
    } catch {
      setLimits(null);
    }
  }, []);

  const refreshOffice = useCallback(async () => {
    try {
      setOffice(await getOffice());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load office");
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await listWorkflows(50));
    } catch {
      /* keep prior list */
    }
  }, []);

  useEffect(() => {
    const immediate = window.setTimeout(() => {
      void refreshOffice();
      void refreshLimits();
      void refreshConversations();
    }, 0);
    const timer = window.setInterval(() => {
      void refreshOffice();
    }, 2000);
    return () => {
      window.clearTimeout(immediate);
      window.clearInterval(timer);
    };
  }, [refreshOffice, refreshLimits, refreshConversations]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([listAgents(), listProviders(), getRoutingPolicy()])
      .then(([nextAgents, nextProviders, policy]) => {
        if (!cancelled) {
          setAgents(nextAgents);
          setProviders(nextProviders);
          setRoutingPolicy(policy);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load agents");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selected) {
      setMailbox(null);
      setMemory([]);
      setDeskArtifacts([]);
      return;
    }
    let cancelled = false;
    void Promise.all([
      getMailbox(selected),
      getMemory(selected),
      listArtifacts({ created_by: selected, limit: 20 }),
    ])
      .then(([nextMailbox, nextMemory, artifacts]) => {
        if (!cancelled) {
          setMailbox(nextMailbox);
          setMemory(nextMemory);
          setDeskArtifacts(artifacts);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Failed to load desk");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  useEffect(() => {
    if (!workflow || TERMINAL_STATUSES.has(workflow.status)) {
      if (workflow && TERMINAL_STATUSES.has(workflow.status)) {
        void refreshConversations();
      }
      return;
    }
    const timer = window.setInterval(() => {
      void getWorkflow(workflow.id)
        .then((next) => {
          setWorkflow(next);
          if (TERMINAL_STATUSES.has(next.status)) {
            void refreshConversations();
          }
        })
        .catch((cause: unknown) => {
          setError(cause instanceof Error ? cause.message : "Failed to refresh workflow");
        });
    }, 750);
    return () => window.clearInterval(timer);
  }, [workflow, refreshConversations]);

  const liveProviders = useMemo(
    () => providers.filter((provider) => !provider.demo),
    [providers],
  );
  const demoProviders = useMemo(
    () => providers.filter((provider) => provider.demo),
    [providers],
  );
  const modelOptions = useMemo(() => {
    const source = liveProviders.some((p) => p.models.length > 0) ? liveProviders : demoProviders;
    return source.flatMap((provider) =>
      provider.models.map((model) => ({
        id: model.id,
        label: model.demo
          ? `${model.id} · Offline demo`
          : `${model.id} · $${model.output_cost_per_million}/M out`,
        cost: model.output_cost_per_million,
        demo: model.demo,
      })),
    );
  }, [liveProviders, demoProviders]);

  const offlineDemo = demoOnly(providers);
  const noModels = !hasUsableModels(providers);

  const freeOnlyBlocked = useMemo(() => {
    if (!freeOnly || offlineDemo) {
      return null;
    }
    const live = liveModels(providers);
    if (live.length === 0) {
      return null;
    }
    const cheap = Math.min(...live.map((m) => m.output_cost_per_million));
    const isCostly = (id: string) => {
      const model = live.find((m) => m.id === id);
      if (!model) {
        return false;
      }
      return model.output_cost_per_million > cheap && model.output_cost_per_million > 0;
    };
    if (routingStrategy === "one" && sharedModel && isCostly(sharedModel)) {
      return "Free Only is on — the selected model is not the cheapest available. Choose Auto or a cheaper model in Advanced.";
    }
    if (routingStrategy === "mixed") {
      const costly = Object.values(modelOverrides).some((id) => isCostly(id));
      if (costly) {
        return "Free Only is on — a pinned model is more expensive than necessary. Switch to Auto or cheaper models.";
      }
    }
    return null;
  }, [freeOnly, offlineDemo, providers, routingStrategy, sharedModel, modelOverrides]);

  const chosen = office?.agents.find((item) => item.agent.id === selected);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (pickAgents && selectedAgents.length === 0) {
        throw new Error("Select at least one agent, or turn off Pick agents.");
      }
      if (freeOnlyBlocked) {
        throw new Error(freeOnlyBlocked);
      }
      const parsedCost = maxCost.trim() === "" ? null : Number(maxCost);
      if (parsedCost !== null && (!Number.isFinite(parsedCost) || parsedCost <= 0)) {
        throw new Error("Budget must be a positive number.");
      }
      const roster = pickAgents ? selectedAgents : agents.map((agent) => agent.id);
      const overrides: Record<string, string> = {};
      if (routingStrategy === "mixed") {
        for (const agentId of roster) {
          const model = modelOverrides[agentId];
          if (model) {
            overrides[agentId] = model;
          }
        }
        if (Object.keys(overrides).length === 0) {
          throw new Error("Mixed routing needs at least one per-agent model.");
        }
      }
      if (routingStrategy === "one" && !sharedModel) {
        throw new Error("One-model routing needs a shared model.");
      }
      const created = await submitTask({
        request: request.trim(),
        max_cost_usd: parsedCost,
        require_approval: requireApproval,
        agent_ids: pickAgents ? selectedAgents : null,
        routing_strategy: routingStrategy,
        shared_model: routingStrategy === "one" ? sharedModel : null,
        model_overrides: routingStrategy === "mixed" ? overrides : {},
      });
      setWorkflow(created);
      setComposerMode("followup");
      setRequest("");
      setTab("home");
      void refreshOffice();
      void refreshConversations();
      void listAgents().then(setAgents);
    } catch (cause) {
      setError(cause instanceof ApiError || cause instanceof Error ? cause.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  };

  const toggleAgent = (agentId: string) => {
    setSelectedAgents((current) =>
      current.includes(agentId)
        ? current.filter((id) => id !== agentId)
        : [...current, agentId],
    );
  };

  const runControl = useCallback(
    async (action: "approve" | "reject" | "retry" | "skip" | "cancel", nodeKey?: string) => {
      if (!workflow) {
        return;
      }
      setError(null);
      setBusy(true);
      try {
        const next =
          action === "cancel"
            ? await cancelWorkflow(workflow.id)
            : await controlNode(workflow.id, nodeKey ?? "", action, {
                reason: action === "reject" ? "rejected from the UI" : null,
              });
        setWorkflow(next);
        void refreshOffice();
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Action failed");
      } finally {
        setBusy(false);
      }
    },
    [refreshOffice, workflow],
  );

  const refreshProviders = useCallback(async () => {
    try {
      setProviders(await listProviders());
    } catch {
      /* keep prior */
    }
  }, []);

  const runProviderAction = useCallback(
    async (providerId: string, action: "connect" | "test" | "refresh" | "disconnect") => {
      setProviderBusy(providerId);
      setProviderMessage(null);
      setError(null);
      try {
        let result;
        if (action === "connect") {
          const key = providerKeys[providerId]?.trim() ?? "";
          if (key.length < 8) {
            throw new Error("Enter an API key (at least 8 characters).");
          }
          result = await connectProvider(providerId, key);
          setProviderKeys((current) => ({ ...current, [providerId]: "" }));
        } else if (action === "test") {
          result = await testProvider(providerId);
        } else if (action === "refresh") {
          result = await refreshProviderModels(providerId);
        } else {
          result = await disconnectProvider(providerId);
        }
        setProviderMessage(`${result.provider.label}: ${result.message}`);
        await refreshProviders();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Provider action failed");
      } finally {
        setProviderBusy(null);
      }
    },
    [providerKeys, refreshProviders],
  );

  const saveAgentBinding = useCallback(
    async (agentId: string, preferredModel: string | null) => {
      setBindingBusy(agentId);
      setError(null);
      try {
        const updated = await setAgentModelBinding(agentId, preferredModel);
        setAgents((current) => current.map((agent) => (agent.id === agentId ? updated : agent)));
        void refreshOffice();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update agent binding");
      } finally {
        setBindingBusy(null);
      }
    },
    [refreshOffice],
  );

  const saveRoutingPolicy = useCallback(async (next: RoutingPolicy) => {
    setPolicyBusy(true);
    setError(null);
    try {
      setRoutingPolicy(await updateRoutingPolicy(next));
      setProviderMessage("Routing policy saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save routing policy");
    } finally {
      setPolicyBusy(false);
    }
  }, []);

  const configuredProviderIds = useMemo(() => {
    const live = providers.filter((item) => item.configured && !item.demo).map((item) => item.name);
    return [
      ...routingPolicy.provider_priority.filter((id) => live.includes(id)),
      ...live.filter((id) => !routingPolicy.provider_priority.includes(id)),
    ];
  }, [providers, routingPolicy.provider_priority]);

  const catalogueModels = useMemo(
    () =>
      providers
        .filter((item) => !item.demo)
        .flatMap((item) => item.models.map((model) => ({ ...model, providerLabel: item.label }))),
    [providers],
  );

  const startNewChat = () => {
    setWorkflow(null);
    setRequest("");
    setComposerMode("new");
    setAdvancedComposer(false);
    setTab("home");
  };

  const openConversation = async (id: string) => {
    setError(null);
    try {
      const full = await getWorkflow(id);
      setWorkflow(full);
      setComposerMode("followup");
      setRequest("");
      setTab("home");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to open chat");
    }
  };

  const openAgent = (agentId: string) => {
    setSelected(agentId);
    setDrawerOpen(true);
  };

  const toggleFree = () => {
    const next = !freeOnly;
    setFreeOnlyState(next);
    setFreeOnly(next);
  };

  const onActor = (value: string) => {
    setActor(value);
    setOperatorId(value);
  };

  return (
    <AppShell
      tab={tab}
      onTab={setTab}
      onNewTask={startNewChat}
    >
      {error && (
        <p className="banner-err" role="alert">
          {error}
        </p>
      )}

      {tab === "home" && (
        <div className="workspace chat">
          <ConversationSidebar
            conversations={conversations}
            activeId={workflow?.id ?? null}
            onSelect={(id) => void openConversation(id)}
            onNew={startNewChat}
          />
          <div className="chat-main">
            <ChatThread
              workflow={workflow}
              busy={busy}
              onOpenWork={() => setTab("work")}
            />
            <TaskComposer
              compact={composerMode === "followup" || !!workflow}
              request={request}
              onRequest={setRequest}
              busy={busy}
              offlineDemo={offlineDemo}
              noModels={noModels}
              onConfigure={() => setTab("settings")}
              onCheckAgain={() => void refreshProviders()}
              advancedOpen={advancedComposer}
              onToggleAdvanced={() => setAdvancedComposer((v) => !v)}
              pickAgents={pickAgents}
              onPickAgents={setPickAgents}
              agents={agents}
              selectedAgents={selectedAgents}
              onToggleAgent={toggleAgent}
              routingStrategy={routingStrategy}
              onRoutingStrategy={setRoutingStrategy}
              sharedModel={sharedModel}
              onSharedModel={setSharedModel}
              modelOverrides={modelOverrides}
              onModelOverride={(agentId, value) => {
                setModelOverrides((current) => {
                  const next = { ...current };
                  if (!value) {
                    delete next[agentId];
                  } else {
                    next[agentId] = value;
                  }
                  return next;
                });
              }}
              modelOptions={modelOptions}
              requireApproval={requireApproval}
              onRequireApproval={setRequireApproval}
              maxCost={maxCost}
              onMaxCost={setMaxCost}
              freeOnlyBlocked={freeOnlyBlocked}
              onSubmit={(event) => void onSubmit(event)}
            />
            <details className="panel" style={{ padding: "8px 12px" }}>
              <summary className="muted" style={{ cursor: "pointer" }}>
                Agents ({office?.agents.length ?? 0})
              </summary>
              <div style={{ marginTop: 12 }}>
                <AgentStrip
                  agents={office?.agents ?? []}
                  selected={selected}
                  onSelect={openAgent}
                />
              </div>
            </details>
          </div>
        </div>
      )}

      {tab === "agents" && (
        <div className="stack-gap">
          <section className="panel">
            <h2 className="panel-title">Agent roster</h2>
            <p className="muted">Click an agent for status, mail, and artifacts.</p>
            <AgentStrip
              agents={office?.agents ?? []}
              selected={selected}
              onSelect={openAgent}
            />
          </section>
        </div>
      )}

      {tab === "work" && (
        <div className="stack-gap">
          {!workflow && (
            <div className="panel empty-state">
              <h3>No active tasks</h3>
              <p>Start a task and your agents will appear here.</p>
              <button type="button" className="px-btn primary" onClick={() => setTab("home")}>
                New task
              </button>
            </div>
          )}
          {workflow && (
            <WorkflowProgress
              workflow={workflow}
              busy={busy}
              onControl={(action, nodeKey) => void runControl(action, nodeKey)}
              showAdvanced={advancedWorkflow}
              onToggleAdvanced={() => setAdvancedWorkflow((v) => !v)}
            />
          )}
        </div>
      )}

      {tab === "messages" && (
        <MessagesPanel
          agents={office?.agents ?? []}
          selected={selected}
          onSelect={(id) => {
            setSelected(id);
            setMailFolder("inbox");
          }}
          mailbox={mailbox}
          folder={mailFolder}
          onFolder={setMailFolder}
          showDev={showMsgDev}
          onToggleDev={() => setShowMsgDev((v) => !v)}
        />
      )}

      {tab === "settings" && (
        <SettingsPanel
          actor={actor}
          onActor={onActor}
          limits={limits}
          providers={providers}
          providerKeys={providerKeys}
          onProviderKey={(id, value) =>
            setProviderKeys((current) => ({ ...current, [id]: value }))
          }
          providerBusy={providerBusy}
          providerMessage={providerMessage}
          onProviderAction={(id, action) => void runProviderAction(id, action)}
          agents={agents}
          modelOptions={modelOptions}
          bindingBusy={bindingBusy}
          onSaveBinding={(id, model) => void saveAgentBinding(id, model)}
          routingPolicy={routingPolicy}
          configuredProviderIds={configuredProviderIds}
          catalogueModels={catalogueModels}
          policyBusy={policyBusy}
          onSavePolicy={(next) => void saveRoutingPolicy(next)}
          advancedOpen={advancedSettings}
          onToggleAdvanced={() => setAdvancedSettings((v) => !v)}
          freeOnly={freeOnly}
          onToggleFree={toggleFree}
        />
      )}

      {drawerOpen && chosen && (
        <AgentDrawer
          item={chosen}
          mailbox={mailbox}
          memory={memory}
          artifacts={deskArtifacts}
          showAdvanced={advancedDrawer}
          onToggleAdvanced={() => setAdvancedDrawer((v) => !v)}
          onClose={() => setDrawerOpen(false)}
        />
      )}
    </AppShell>
  );
}
