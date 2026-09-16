/** Provider showcase metadata for Settings (labels, pricing tier, blurbs). */

export type ProviderMeta = {
  id: string;
  brand: string;
  blurb: string;
  tier: "paid" | "freemium" | "gateway" | "demo";
  modelsHint: string;
  accent: string;
};

export const PROVIDER_META: Record<string, ProviderMeta> = {
  openai: {
    id: "openai",
    brand: "OpenAI / ChatGPT",
    blurb: "GPT-4o and reasoning models for coding, analysis, and chat.",
    tier: "paid",
    modelsHint: "GPT-4o · o-series",
    accent: "#10a37f",
  },
  anthropic: {
    id: "anthropic",
    brand: "Claude",
    blurb: "Anthropic Claude — strong coding, long context, and careful reasoning.",
    tier: "paid",
    modelsHint: "Sonnet · Opus · Haiku",
    accent: "#d4a27f",
  },
  google: {
    id: "google",
    brand: "Google Gemini",
    blurb: "Gemini Flash & Pro via Google AI Studio API keys.",
    tier: "freemium",
    modelsHint: "Flash · Pro latest",
    accent: "#8ab4f8",
  },
  moonshot: {
    id: "moonshot",
    brand: "Kimi",
    blurb: "Moonshot Kimi — long-context chat and coding from the Kimi lab.",
    tier: "paid",
    modelsHint: "Kimi K2.6 · Moonshot 128K",
    accent: "#1a1a1a",
  },
  groq: {
    id: "groq",
    brand: "Groq",
    blurb: "Ultra-fast Llama and Mixtral inference — great for demos.",
    tier: "freemium",
    modelsHint: "Llama 3.3 · Mixtral",
    accent: "#f55036",
  },
  deepseek: {
    id: "deepseek",
    brand: "DeepSeek",
    blurb: "High-value coding and reasoning models.",
    tier: "paid",
    modelsHint: "Chat · Reasoner",
    accent: "#4d6bfe",
  },
  xai: {
    id: "xai",
    brand: "Grok",
    blurb: "xAI Grok models for general and coding work.",
    tier: "paid",
    modelsHint: "Grok-2",
    accent: "#e8e8e8",
  },
  mistral: {
    id: "mistral",
    brand: "Mistral",
    blurb: "European open-weight class models via Mistral API.",
    tier: "paid",
    modelsHint: "Large · Small",
    accent: "#ff7000",
  },
  cohere: {
    id: "cohere",
    brand: "Cohere",
    blurb: "Command R / R+ for enterprise RAG and agent workflows.",
    tier: "paid",
    modelsHint: "Command R+ · Command R",
    accent: "#39594d",
  },
  perplexity: {
    id: "perplexity",
    brand: "Perplexity",
    blurb: "Sonar models with live web grounding for research briefs.",
    tier: "paid",
    modelsHint: "Sonar Pro · Sonar",
    accent: "#22b8cd",
  },
  together: {
    id: "together",
    brand: "Together AI",
    blurb: "Hosted open models (Llama and friends) at competitive rates.",
    tier: "paid",
    modelsHint: "Llama 3.3 70B",
    accent: "#0f6fff",
  },
  qwen: {
    id: "qwen",
    brand: "Qwen",
    blurb: "Alibaba Qwen via DashScope — strong multilingual coding models.",
    tier: "paid",
    modelsHint: "Qwen Plus · Turbo",
    accent: "#615ced",
  },
  openrouter: {
    id: "openrouter",
    brand: "OpenRouter",
    blurb: "One key for many labs — route across vendors.",
    tier: "gateway",
    modelsHint: "Multi-provider gateway",
    accent: "#a78bfa",
  },
  fake: {
    id: "fake",
    brand: "Offline demo",
    blurb: "Simulated responses when no live key is connected.",
    tier: "demo",
    modelsHint: "Local mock",
    accent: "#5c6575",
  },
};

export function providerMeta(id: string): ProviderMeta {
  return (
    PROVIDER_META[id] ?? {
      id,
      brand: id,
      blurb: "Connect with your API key.",
      tier: "paid",
      modelsHint: "API",
      accent: "#3dd6c6",
    }
  );
}

export function tierLabel(tier: ProviderMeta["tier"]): string {
  switch (tier) {
    case "paid":
      return "Paid";
    case "freemium":
      return "Free tier available";
    case "gateway":
      return "Multi-model";
    case "demo":
      return "Offline";
  }
}
