"use client";

import { providerMeta } from "@/lib/providers";

const LOGO_IDS = new Set([
  "openai",
  "anthropic",
  "google",
  "moonshot",
  "groq",
  "deepseek",
  "xai",
  "mistral",
  "cohere",
  "perplexity",
  "together",
  "qwen",
  "openrouter",
  "fake",
]);

export function providerLogoSrc(providerId: string): string {
  const id = LOGO_IDS.has(providerId) ? providerId : "fake";
  return `/providers/${id}.svg`;
}

/** Extract provider id from a catalogue model id like `openai:gpt-4o`. */
export function providerIdFromModel(modelId: string | null | undefined): string | null {
  if (!modelId || !modelId.includes(":")) {
    return null;
  }
  const id = modelId.split(":")[0];
  return id || null;
}

export function ProviderIcon({
  providerId,
  size = 28,
  className = "",
  title,
}: {
  providerId: string;
  size?: number;
  className?: string;
  title?: string;
}) {
  const meta = providerMeta(providerId);
  const label = title ?? meta.brand;

  return (
    <span
      className={`provider-icon ${className}`.trim()}
      style={{ width: size, height: size }}
      title={label}
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- local brand SVG marks */}
      <img src={providerLogoSrc(providerId)} alt="" width={size} height={size} />
      <span className="visually-hidden">{label}</span>
    </span>
  );
}
