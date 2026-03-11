const OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions";
const OPENROUTER_TIMEOUT_MS = 30000;

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

type OpenRouterContentPart = {
  type?: string;
  text?: string;
};

function extractCompletionText(content: string | OpenRouterContentPart[] | null | undefined): string {
  if (typeof content === "string") {
    return content.trim();
  }

  if (Array.isArray(content)) {
    const text = content
      .map((part) => {
        if (!part || typeof part !== "object") return "";
        if (part.type && part.type !== "text") return "";
        return typeof part.text === "string" ? part.text : "";
      })
      .join("")
      .trim();

    return text;
  }

  return "";
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

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), OPENROUTER_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(OPENROUTER_API_URL, {
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
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`OpenRouter request timed out after ${OPENROUTER_TIMEOUT_MS}ms`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`OpenRouter error ${response.status}: ${errorBody.slice(0, 400)}`);
  }

  const payload = (await response.json()) as {
    choices?: Array<{
      message?: {
        content?: string | OpenRouterContentPart[] | null;
      };
    }>;
  };

  const text = extractCompletionText(payload.choices?.[0]?.message?.content);
  if (text.length === 0) {
    throw new Error("OpenRouter returned an empty completion");
  }

  return text;
}
