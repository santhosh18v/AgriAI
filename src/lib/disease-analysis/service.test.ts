import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const analyzeImageWithGeminiMock = vi.fn();
vi.mock("@/lib/gemini", () => ({
  analyzeImageWithGemini: (...args: unknown[]) => analyzeImageWithGeminiMock(...args),
}));

const predictWithCustomMlMock = vi.fn();
vi.mock("./providers/custom-ml", () => ({
  predictWithCustomMl: (...args: unknown[]) => predictWithCustomMlMock(...args),
}));

import { _resetDiseaseAnalysisConfigCacheForTests } from "./config";
import { runDiseaseAnalysis } from "./service";
import { CustomMlNormalizedResult, DiseaseAnalysisError } from "./types";

const ENV_KEYS = [
  "DISEASE_ANALYSIS_PROVIDER",
  "CUSTOM_ML_ENABLED",
  "CUSTOM_ML_SERVICE_URL",
  "CUSTOM_ML_REQUEST_TIMEOUT_MS",
  "CUSTOM_ML_FALLBACK_TO_GEMINI",
  "CUSTOM_ML_REQUIRE_READY_CHECK",
] as const;
let savedEnv: Record<string, string | undefined>;

function makeFile(): File {
  return new File([new Uint8Array([1, 2, 3])], "leaf.jpg", { type: "image/jpeg" });
}

function makeCustomMlResult(overrides: Partial<CustomMlNormalizedResult> = {}): CustomMlNormalizedResult {
  return {
    disease: "Tomato Late Blight",
    classIndex: 2,
    crop: "Tomato",
    condition: "Late Blight",
    healthy: false,
    modelConfidence: 0.98,
    accepted: true,
    uncertain: false,
    confidenceLabel: "model confidence",
    productionCalibrated: false,
    supportedClass: true,
    confidenceThreshold: 0.5,
    confidenceMethod: "maximum_softmax_probability",
    topPredictions: [{ className: "Tomato Late Blight", classIndex: 2, modelConfidence: 0.98 }],
    model: { architecture: "efficientnet_b0", classCount: 6 },
    limitations: ["Model confidence is not certainty or probability of truth."],
    ...overrides,
  };
}

beforeEach(() => {
  savedEnv = {};
  for (const key of ENV_KEYS) {
    savedEnv[key] = process.env[key];
    delete process.env[key];
  }
  _resetDiseaseAnalysisConfigCacheForTests();
  analyzeImageWithGeminiMock.mockReset();
  predictWithCustomMlMock.mockReset();
  analyzeImageWithGeminiMock.mockResolvedValue(
    "DIAGNOSIS: Healthy plant\nSEVERITY: Healthy\nCONFIDENCE: 80\nTREATMENT: none\nPREVENTION: none"
  );
});

afterEach(() => {
  for (const key of ENV_KEYS) {
    if (savedEnv[key] === undefined) delete process.env[key];
    else process.env[key] = savedEnv[key];
  }
  _resetDiseaseAnalysisConfigCacheForTests();
});

describe("provider selection", () => {
  it("uses Gemini when the feature flag is disabled (default)", async () => {
    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("gemini");
    expect(analyzeImageWithGeminiMock).toHaveBeenCalledTimes(1);
    expect(predictWithCustomMlMock).not.toHaveBeenCalled();
  });

  it("uses custom-ml when enabled and selected", async () => {
    process.env.CUSTOM_ML_ENABLED = "true";
    process.env.DISEASE_ANALYSIS_PROVIDER = "custom-ml";
    predictWithCustomMlMock.mockResolvedValueOnce(makeCustomMlResult());

    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("custom-ml");
    expect(outcome.customMl).toBeDefined();
    expect(predictWithCustomMlMock).toHaveBeenCalledTimes(1);
    expect(analyzeImageWithGeminiMock).not.toHaveBeenCalled();
  });

  it("Gemini-only mode is unaffected by custom-ml code paths existing", async () => {
    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("gemini");
    expect(outcome.customMl).toBeUndefined();
    expect(outcome.fallback).toBeUndefined();
  });
});

describe("mapCustomMlToLegacy disclaimer text (via runDiseaseAnalysis)", () => {
  beforeEach(() => {
    process.env.CUSTOM_ML_ENABLED = "true";
    process.env.DISEASE_ANALYSIS_PROVIDER = "custom-ml";
  });

  it("treatment/prevention are safe disclaimers, never a fabricated verified recommendation", async () => {
    predictWithCustomMlMock.mockResolvedValueOnce(makeCustomMlResult({ healthy: false }));
    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });

    expect(outcome.legacy.treatment).toMatch(/does not yet generate a treatment plan/i);
    expect(outcome.legacy.treatment).toMatch(/consult a local agricultural extension/i);
    expect(outcome.legacy.prevention).toMatch(/does not yet generate prevention guidance/i);
  });

  it("healthy predictions get a 'no treatment needed' disclaimer, not a fabricated treatment plan", async () => {
    predictWithCustomMlMock.mockResolvedValueOnce(
      makeCustomMlResult({ disease: "Tomato Healthy", crop: "Tomato", condition: "Healthy", healthy: true })
    );
    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.legacy.treatment).toMatch(/no treatment needed/i);
    expect(outcome.legacy.severity).toBe("healthy");
  });

  it("rawResponse is a factual echo of structured data, containing no service URL or secrets", async () => {
    predictWithCustomMlMock.mockResolvedValueOnce(makeCustomMlResult());
    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.legacy.rawResponse).not.toMatch(/https?:\/\//);
    expect(outcome.legacy.rawResponse).not.toContain("127.0.0.1");
  });
});

describe("fallback policy", () => {
  beforeEach(() => {
    process.env.CUSTOM_ML_ENABLED = "true";
    process.env.DISEASE_ANALYSIS_PROVIDER = "custom-ml";
  });

  it("falls back to Gemini when custom-ml is unavailable and fallback is enabled", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "true";
    predictWithCustomMlMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("ML_SERVICE_UNAVAILABLE", "unavailable", 503)
    );

    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("gemini");
    expect(outcome.fallback).toEqual({
      primaryProvider: "custom-ml",
      fallbackProvider: "gemini",
      fallbackReason: "service_unavailable",
    });
    expect(analyzeImageWithGeminiMock).toHaveBeenCalledTimes(1);
  });

  it("returns a safe error (no fallback) when custom-ml is unavailable and fallback is disabled", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "false";
    predictWithCustomMlMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("ML_SERVICE_UNAVAILABLE", "unavailable", 503)
    );

    await expect(runDiseaseAnalysis({ file: makeFile(), query: "q" })).rejects.toMatchObject({
      code: "ML_SERVICE_UNAVAILABLE",
    });
    expect(analyzeImageWithGeminiMock).not.toHaveBeenCalled();
  });

  it("does NOT fall back to Gemini for a user-caused 4xx error (invalid image), even with fallback enabled", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "true";
    predictWithCustomMlMock.mockRejectedValueOnce(new DiseaseAnalysisError("INVALID_IMAGE", "bad image", 400));

    await expect(runDiseaseAnalysis({ file: makeFile(), query: "q" })).rejects.toMatchObject({
      code: "INVALID_IMAGE",
    });
    expect(analyzeImageWithGeminiMock).not.toHaveBeenCalled();
  });

  it("does NOT fall back to Gemini for an oversized-image 4xx error", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "true";
    predictWithCustomMlMock.mockRejectedValueOnce(new DiseaseAnalysisError("IMAGE_TOO_LARGE", "too big", 413));

    await expect(runDiseaseAnalysis({ file: makeFile(), query: "q" })).rejects.toMatchObject({
      code: "IMAGE_TOO_LARGE",
    });
    expect(analyzeImageWithGeminiMock).not.toHaveBeenCalled();
  });

  it("falls back on a malformed upstream response", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "true";
    predictWithCustomMlMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("ML_UPSTREAM_INVALID_RESPONSE", "bad shape", 502)
    );

    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("gemini");
    expect(outcome.fallback?.fallbackReason).toBe("malformed_upstream");
  });

  it("falls back on timeout", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "true";
    predictWithCustomMlMock.mockRejectedValueOnce(new DiseaseAnalysisError("ML_SERVICE_TIMEOUT", "timed out", 504));

    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("gemini");
    expect(outcome.fallback?.fallbackReason).toBe("timeout");
  });

  it("falls back with fallbackReason 'service_not_ready' when the ml-service reports not ready (Milestone M9)", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "true";
    predictWithCustomMlMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("ML_SERVICE_NOT_READY", "not ready", 503)
    );

    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("gemini");
    expect(outcome.fallback?.fallbackReason).toBe("service_not_ready");
  });
});

describe("uncertain predictions", () => {
  beforeEach(() => {
    process.env.CUSTOM_ML_ENABLED = "true";
    process.env.DISEASE_ANALYSIS_PROVIDER = "custom-ml";
  });

  it("preserves the uncertain custom-ml result as uncertain (never silently confirmed)", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "false";
    predictWithCustomMlMock.mockResolvedValueOnce(
      makeCustomMlResult({ accepted: false, uncertain: true, modelConfidence: 0.3 })
    );

    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("custom-ml");
    expect(outcome.customMl?.uncertain).toBe(true);
    expect(outcome.customMl?.accepted).toBe(false);
    expect(analyzeImageWithGeminiMock).not.toHaveBeenCalled();
  });

  it("attaches a separately-labelled secondary Gemini opinion when uncertain + fallback enabled, without replacing the primary result", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "true";
    predictWithCustomMlMock.mockResolvedValueOnce(
      makeCustomMlResult({ accepted: false, uncertain: true, modelConfidence: 0.3 })
    );

    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });

    // Primary provider/result stays custom-ml and uncertain -- not overwritten.
    expect(outcome.provider).toBe("custom-ml");
    expect(outcome.customMl?.uncertain).toBe(true);
    expect(outcome.legacy.diagnosis).toBe("Tomato Late Blight");

    // Secondary opinion is present and separately labelled.
    expect(outcome.secondaryOpinion?.provider).toBe("gemini");
    expect(outcome.secondaryOpinion?.legacy).toBeDefined();
    expect(outcome.fallback?.fallbackReason).toBe("uncertain_prediction");
    expect(analyzeImageWithGeminiMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the primary uncertain result even if the secondary Gemini opinion call fails", async () => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = "true";
    predictWithCustomMlMock.mockResolvedValueOnce(
      makeCustomMlResult({ accepted: false, uncertain: true, modelConfidence: 0.3 })
    );
    analyzeImageWithGeminiMock.mockRejectedValueOnce(new Error("gemini down"));

    const outcome = await runDiseaseAnalysis({ file: makeFile(), query: "q" });
    expect(outcome.provider).toBe("custom-ml");
    expect(outcome.customMl?.uncertain).toBe(true);
    expect(outcome.secondaryOpinion).toBeUndefined();
    expect(outcome.fallback).toBeUndefined();
  });
});
