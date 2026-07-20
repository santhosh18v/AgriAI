import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth-options";

const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || "http://localhost:11434";
const OLLAMA_MODEL = process.env.OLLAMA_MODEL || "qwen3:8b";
const HEALTH_TIMEOUT_MS = 5000;

interface OllamaTagsResponse {
  models: { name: string; model: string; [key: string]: unknown }[];
}

export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  const start = Date.now();

  try {
    const res = await fetch(`${OLLAMA_BASE_URL}/api/tags`, { signal: controller.signal });
    const latencyMs = Date.now() - start;

    if (!res.ok) {
      return NextResponse.json({
        status: "down",
        modelAvailable: false,
        configuredModel: OLLAMA_MODEL,
        latencyMs,
        error: `HTTP ${res.status}`,
      });
    }

    const data: OllamaTagsResponse = await res.json();
    const modelAvailable =
      data.models?.some((m) => m.name === OLLAMA_MODEL || m.model === OLLAMA_MODEL) ?? false;

    return NextResponse.json({
      status: "up",
      modelAvailable,
      configuredModel: OLLAMA_MODEL,
      latencyMs,
    });
  } catch (err: any) {
    const latencyMs = Date.now() - start;
    const timedOut = err?.name === "AbortError";
    return NextResponse.json({
      status: "down",
      modelAvailable: false,
      configuredModel: OLLAMA_MODEL,
      latencyMs,
      error: timedOut ? "timeout" : "connection refused",
    });
  } finally {
    clearTimeout(timeoutId);
  }
}
