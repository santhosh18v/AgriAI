/**
 * Disease-analysis provider orchestrator (Milestone M8).
 *
 * Only ever invoked for the crop-disease + image case (see route.ts) --
 * pest/soil/weather/waste/general analysis and text-only/Groq requests are
 * untouched and never reach this module. Selects the configured provider,
 * applies the fallback policy (Section 8 of the M8 spec: infrastructure
 * failures only, never for user-caused 4xx errors), and always returns a
 * `legacy` result so the existing UI keeps working unmodified regardless
 * of which provider actually served the request.
 */

import { analyzeImageWithGemini } from "@/lib/gemini";

import { classBreakdown } from "./class-mapping";
import { DiseaseAnalysisConfig, getDiseaseAnalysisConfig } from "./config";
import { parseAIResponse } from "./providers/gemini";
import { predictWithCustomMl } from "./providers/custom-ml";
import {
  CustomMlNormalizedResult,
  DiseaseAnalysisError,
  DiseaseAnalysisOutcome,
  FallbackReason,
  LegacyAnalysisResult,
} from "./types";

export interface DiseaseAnalysisRequest {
  file: File;
  query: string;
  cropName?: string;
}

const INFRASTRUCTURE_ERROR_CODES = new Set([
  "ML_SERVICE_UNAVAILABLE",
  "ML_SERVICE_TIMEOUT",
  "ML_SERVICE_NOT_READY",
  "ML_UPSTREAM_INVALID_RESPONSE",
]);

function isInfrastructureFailure(err: unknown): err is DiseaseAnalysisError {
  return err instanceof DiseaseAnalysisError && INFRASTRUCTURE_ERROR_CODES.has(err.code);
}

function mapErrorCodeToFallbackReason(code: string): FallbackReason {
  switch (code) {
    case "ML_SERVICE_TIMEOUT":
      return "timeout";
    case "ML_SERVICE_NOT_READY":
      return "not_ready";
    case "ML_UPSTREAM_INVALID_RESPONSE":
      return "malformed_upstream";
    default:
      return "service_unavailable";
  }
}

function mapCustomMlToLegacy(result: CustomMlNormalizedResult): LegacyAnalysisResult {
  const severity: LegacyAnalysisResult["severity"] = result.healthy ? "healthy" : "medium";
  const confidence = Math.round(result.modelConfidence * 100);

  const treatment = result.healthy
    ? "No treatment needed -- the custom model did not detect signs of disease in this image."
    : "This condition was identified by AgriAI's custom disease-detection model, which identifies the " +
      "condition only and does not yet generate a treatment plan. Consult a local agricultural extension " +
      "service, or re-run analysis with Gemini for general guidance.";

  const prevention =
    "Follow standard crop-specific sanitation, spacing, and monitoring practices for this condition. " +
    "This model does not yet generate prevention guidance.";

  const expertAdvice = result.uncertain
    ? "The custom model returned a low-confidence result. Please capture a clearer leaf image or use expert review."
    : undefined;

  const topSummary = result.topPredictions
    .map((p) => `${p.className} ${(p.modelConfidence * 100).toFixed(2)}%`)
    .join(", ");
  const rawResponse =
    `Custom ML model prediction: ${result.disease} ` +
    `(model confidence ${(result.modelConfidence * 100).toFixed(2)}%, ${result.accepted ? "accepted" : "uncertain"}). ` +
    `Top predictions: ${topSummary}.`;

  return {
    diagnosis: result.disease,
    severity,
    confidence,
    treatment,
    prevention,
    expertAdvice,
    rawResponse,
  };
}

function buildDiseaseGeminiPrompt(query: string, cropName?: string): string {
  return `Analyze this crop/plant image and provide:

1. DIAGNOSIS: What disease, pest, or issue do you see?
2. SEVERITY: Rate as Critical/High/Medium/Low/Healthy
3. CONFIDENCE: Your confidence percentage (0-100)
4. AFFECTED AREA: What percentage of the plant/area is affected?
5. TREATMENT: Step-by-step treatment plan
6. PREVENTION: Future prevention measures
7. EXPERT ADVICE: Should they consult an expert? When?

Additional context from user: "${query}"
${cropName ? `Crop: ${cropName}` : ""}

Please structure your response clearly with these sections.`;
}

async function analyzeWithGemini(request: DiseaseAnalysisRequest): Promise<LegacyAnalysisResult> {
  const bytes = await request.file.arrayBuffer();
  const base64 = Buffer.from(bytes).toString("base64");
  const mimeType = request.file.type;
  const prompt = buildDiseaseGeminiPrompt(request.query, request.cropName);
  const rawResponse = await analyzeImageWithGemini(base64, mimeType, prompt);
  return { ...parseAIResponse(rawResponse), rawResponse };
}

async function analyzeWithCustomMl(
  config: DiseaseAnalysisConfig,
  request: DiseaseAnalysisRequest
): Promise<DiseaseAnalysisOutcome> {
  const customMl = await predictWithCustomMl(config, request.file);
  const legacy = mapCustomMlToLegacy(customMl);

  if (customMl.uncertain && config.customMlFallbackToGemini) {
    // Optional uncertain-result fallback: the primary custom-ml result
    // stays exactly as returned (uncertain, not accepted) -- Gemini is
    // consulted only as a clearly-separate secondary opinion, never a
    // silent replacement. If the secondary call itself fails, that's not
    // fatal: the primary (uncertain) custom-ml result is still valid and
    // is returned regardless.
    try {
      const secondaryLegacy = await analyzeWithGemini(request);
      return {
        provider: "custom-ml",
        legacy,
        customMl,
        fallback: {
          primaryProvider: "custom-ml",
          fallbackProvider: "gemini",
          fallbackReason: "uncertain_prediction",
        },
        secondaryOpinion: { provider: "gemini", legacy: secondaryLegacy },
      };
    } catch {
      // Secondary opinion unavailable -- fall through to the primary result.
    }
  }

  return { provider: "custom-ml", legacy, customMl };
}

export async function runDiseaseAnalysis(request: DiseaseAnalysisRequest): Promise<DiseaseAnalysisOutcome> {
  const config = getDiseaseAnalysisConfig();

  if (config.provider === "gemini") {
    const legacy = await analyzeWithGemini(request);
    return { provider: "gemini", legacy };
  }

  // config.provider === "custom-ml" (config construction already guarantees
  // customMlEnabled === true whenever this is reachable -- see config.ts).
  try {
    return await analyzeWithCustomMl(config, request);
  } catch (err) {
    if (isInfrastructureFailure(err) && config.customMlFallbackToGemini) {
      const legacy = await analyzeWithGemini(request);
      return {
        provider: "gemini",
        legacy,
        fallback: {
          primaryProvider: "custom-ml",
          fallbackProvider: "gemini",
          fallbackReason: mapErrorCodeToFallbackReason(err.code),
        },
      };
    }
    // User-caused 4xx (INVALID_IMAGE/IMAGE_TOO_LARGE/UNSUPPORTED_MEDIA_TYPE)
    // must never trigger fallback, and infrastructure failures with
    // fallback disabled must propagate as a safe error -- both cases
    // simply re-throw for route.ts to translate into the stable error
    // contract.
    throw err;
  }
}

// Re-exported for callers that only need the crop/condition/healthy
// breakdown without running a full analysis (e.g. tests).
export { classBreakdown };
