/**
 * Free-Only helpers for model selection UX.
 * Live (non-demo) models only; prefers $0 output, else cheapest.
 */

import type { ModelView, ProviderStatus } from "./types";

const FREE_ONLY_KEY = "agentorch.freeOnly";

export function getFreeOnly(): boolean {
  if (typeof window === "undefined") {
    return true;
  }
  const stored = window.localStorage.getItem(FREE_ONLY_KEY);
  if (stored === null) {
    return true;
  }
  return stored === "true";
}

export function setFreeOnly(value: boolean): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(FREE_ONLY_KEY, value ? "true" : "false");
}

export function liveModels(providers: ProviderStatus[]): ModelView[] {
  return providers
    .filter((provider) => !provider.demo && provider.configured)
    .flatMap((provider) => provider.models.filter((model) => !model.demo));
}

export function demoOnly(providers: ProviderStatus[]): boolean {
  const live = liveModels(providers);
  const hasDemo = providers.some((provider) => provider.demo && provider.models.length > 0);
  return live.length === 0 && hasDemo;
}

export function hasUsableModels(providers: ProviderStatus[]): boolean {
  if (liveModels(providers).length > 0) {
    return true;
  }
  return providers.some((provider) => provider.demo && provider.models.length > 0);
}

/** Prefer zero-cost, else cheapest by output $/M. */
export function pickPreferredFreeModel(providers: ProviderStatus[]): ModelView | null {
  const models = liveModels(providers);
  if (models.length === 0) {
    return null;
  }
  const free = models.filter((model) => model.output_cost_per_million === 0);
  const pool = free.length > 0 ? free : models;
  return pool.reduce((best, model) =>
    model.output_cost_per_million < best.output_cost_per_million ? model : best,
  );
}

export function modelIsExpensive(model: ModelView, freeOnly: boolean): boolean {
  if (!freeOnly || model.demo) {
    return false;
  }
  if (model.output_cost_per_million === 0) {
    return false;
  }
  // Relative: expensive if above the cheapest live option significantly
  return model.output_cost_per_million > 0;
}

export function shortAgentName(agentId: string): string {
  return agentId.replace(/-agent$/, "").replace(/-/g, " ");
}

export function messagePreview(content: Record<string, unknown>, fallback: string): string {
  const candidate =
    content.summary ?? content.issue ?? content.question ?? content.query ?? content.answer;
  return String(candidate ?? fallback);
}

export function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export type AiModeChip = "free" | "offline" | "configure";

export function resolveAiMode(providers: ProviderStatus[], freeOnly: boolean): AiModeChip {
  if (demoOnly(providers)) {
    return "offline";
  }
  if (liveModels(providers).length === 0) {
    return "configure";
  }
  if (freeOnly) {
    return "free";
  }
  return "free";
}
