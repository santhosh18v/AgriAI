const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || "http://localhost:11434";
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || "qwen3:8b";
const OLLAMA_TIMEOUT_MS = Number(process.env.OLLAMA_TIMEOUT_MS) || 30000;

const AGRI_SYSTEM_PROMPT = `You are AgriAI, an agricultural assistant helping farmers with crop, soil, pest, and general farming questions.

Safety rules you must always follow:
- Never invent specific pesticide, fertilizer, or chemical dosages, application rates, or product names. If asked for a dosage, give general guidance only and explicitly tell the user to confirm the exact rate with a local agricultural extension officer, the product label, or a certified agronomist before applying anything.
- Clearly communicate uncertainty. If you are not confident about a fact (crop variety behavior, regional pest pressure, local regulations, weather-dependent advice), say so plainly instead of guessing.
- For any decision with significant financial, safety, or crop-health consequences (large-scale spraying, disease treatment, irrigation changes, loan/insurance decisions), recommend the user verify with a qualified expert (agronomist, extension service, veterinarian for livestock) before acting.
- Be concise, practical, and use simple language suitable for farmers who may not have technical backgrounds.`;

interface OllamaChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface OllamaChatRequest {
  model: string;
  messages: OllamaChatMessage[];
  stream: false;
  options?: {
    temperature?: number;
    num_predict?: number;
  };
}

interface OllamaChatResponse {
  model: string;
  created_at: string;
  message: { role: string; content: string };
  done: boolean;
}

export async function chatWithOllama(
  message: string,
  systemPrompt?: string
): Promise<string> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), OLLAMA_TIMEOUT_MS);

  try {
    const body: OllamaChatRequest = {
      model: OLLAMA_MODEL,
      messages: [
        { role: "system", content: systemPrompt || AGRI_SYSTEM_PROMPT },
        { role: "user", content: message },
      ],
      stream: false,
      options: { temperature: 0.3, num_predict: 1024 },
    };

    let res: Response;
    try {
      res = await fetch(`${OLLAMA_BASE_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (err: any) {
      if (err?.name === "AbortError") {
        throw new Error(
          `Ollama request timed out after ${OLLAMA_TIMEOUT_MS}ms. Is the ${OLLAMA_MODEL} model loaded and responsive?`
        );
      }
      throw new Error(
        `Could not reach Ollama at ${OLLAMA_BASE_URL}. Make sure Ollama is running ("ollama serve") and the model is pulled ("ollama pull ${OLLAMA_MODEL}").`
      );
    }

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Ollama returned ${res.status} ${res.statusText}: ${text.slice(0, 300)}`);
    }

    let data: OllamaChatResponse;
    try {
      data = await res.json();
    } catch {
      throw new Error("Ollama returned a malformed (non-JSON) response body.");
    }

    const content = data?.message?.content;
    if (!content) {
      throw new Error("Ollama response did not contain a message.content field.");
    }
    return content;
  } finally {
    clearTimeout(timeoutId);
  }
}
