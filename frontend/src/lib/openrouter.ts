const OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions";

export type OpenRouterMessage = {
  role: "system" | "user" | "assistant";
  content: string;
};

type OpenRouterCompletionArgs = {
  model: string;
  messages: OpenRouterMessage[];
  maxTokens: number;
  temperature?: number;
  reasoning?: { effort: "high" | "medium" | "low" };
};

function getOpenRouterApiKey(): string | null {
  const candidates = [
    process.env.OPENROUTER_API_KEY,
    process.env.OPENROUTER_KEY,
    process.env.OR_API_KEY,
  ];

  for (const value of candidates) {
    if (typeof value !== "string") continue;
    const trimmed = value.trim();
    if (trimmed.length > 0) return trimmed;
  }

  return null;
}

export function hasOpenRouterApiKey(): boolean {
  return getOpenRouterApiKey() !== null;
}

export async function openRouterCompleteText({
  model,
  messages,
  maxTokens,
  temperature = 0.0,
  reasoning,
}: OpenRouterCompletionArgs): Promise<string> {
  const apiKey = getOpenRouterApiKey();
  if (!apiKey) {
    throw new Error("OpenRouter API key not configured");
  }

  const response = await fetch(OPENROUTER_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": process.env.NEXT_PUBLIC_APP_URL || "https://zinc-fusion-v15.vercel.app",
      "X-OpenRouter-Title": "ZINC-FUSION-V15",
    },
    body: JSON.stringify({
      model,
      messages,
      max_tokens: maxTokens,
      temperature,
      ...(reasoning ? { reasoning } : {}),
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`OpenRouter error ${response.status}: ${errorBody.slice(0, 400)}`);
  }

  const payload = (await response.json()) as {
    choices?: Array<{
      message?: {
        content?: string | null;
      };
    }>;
  };

  const text = payload.choices?.[0]?.message?.content;
  if (typeof text !== "string" || text.trim().length === 0) {
    throw new Error("OpenRouter returned an empty completion");
  }

  return text;
}
