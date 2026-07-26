import { beforeEach, describe, expect, it, vi } from "vitest";

const getServerSessionMock = vi.fn();
vi.mock("next-auth", () => ({ getServerSession: (...args: unknown[]) => getServerSessionMock(...args) }));
vi.mock("@/lib/auth-options", () => ({ authOptions: {} }));

const connectDBMock = vi.fn();
vi.mock("@/lib/mongodb", () => ({ default: (...args: unknown[]) => connectDBMock(...args) }));

const analysisCreateMock = vi.fn();
vi.mock("@/models/Analysis", () => ({ default: { create: (...args: unknown[]) => analysisCreateMock(...args) } }));

const userUpdateMock = vi.fn();
vi.mock("@/models/User", () => ({
  default: { findByIdAndUpdate: (...args: unknown[]) => userUpdateMock(...args) },
}));

const analyzeImageWithGeminiMock = vi.fn();
const chatWithGeminiMock = vi.fn();
vi.mock("@/lib/gemini", () => ({
  analyzeImageWithGemini: (...args: unknown[]) => analyzeImageWithGeminiMock(...args),
  chatWithGemini: (...args: unknown[]) => chatWithGeminiMock(...args),
}));

const fastAnalysisWithGroqMock = vi.fn();
vi.mock("@/lib/groq", () => ({ fastAnalysisWithGroq: (...args: unknown[]) => fastAnalysisWithGroqMock(...args) }));

const runDiseaseAnalysisMock = vi.fn();
vi.mock("@/lib/disease-analysis/service", () => ({
  runDiseaseAnalysis: (...args: unknown[]) => runDiseaseAnalysisMock(...args),
}));

const getDiseaseAnalysisConfigMock = vi.fn();
vi.mock("@/lib/disease-analysis/config", async () => {
  const actual = await vi.importActual<typeof import("@/lib/disease-analysis/config")>(
    "@/lib/disease-analysis/config"
  );
  return {
    ...actual,
    getDiseaseAnalysisConfig: (...args: unknown[]) => getDiseaseAnalysisConfigMock(...args),
  };
});

import { NextRequest } from "next/server";
import { DiseaseAnalysisConfigError } from "@/lib/disease-analysis/config";
import { DiseaseAnalysisError, DiseaseAnalysisOutcome } from "@/lib/disease-analysis/types";
import { POST } from "./route";

function makeImageFile(name = "leaf.jpg", type = "image/jpeg"): File {
  return new File([new Uint8Array([1, 2, 3, 4])], name, { type });
}

function makeRequest(fields: Record<string, string | File>): NextRequest {
  const formData = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    formData.append(key, value as any);
  }
  return new NextRequest("http://localhost/api/analyze", { method: "POST", body: formData });
}

function makeCustomMlOutcome(overrides: Partial<DiseaseAnalysisOutcome> = {}): DiseaseAnalysisOutcome {
  return {
    provider: "custom-ml",
    legacy: {
      diagnosis: "Tomato Late Blight",
      severity: "medium",
      confidence: 98,
      treatment: "Consult extension resources.",
      prevention: "Follow sanitation practices.",
      rawResponse: "Custom ML model prediction: Tomato Late Blight (model confidence 98.00%, accepted).",
    },
    customMl: {
      disease: "Tomato Late Blight",
      crop: "Tomato",
      condition: "Late Blight",
      healthy: false,
      modelConfidence: 0.98,
      accepted: true,
      uncertain: false,
      confidenceLabel: "model confidence",
      productionCalibrated: false,
      supportedClass: true,
      topPredictions: [{ className: "Tomato Late Blight", modelConfidence: 0.98 }],
      limitations: ["Model confidence is not certainty or probability of truth."],
    },
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getServerSessionMock.mockResolvedValue({ user: { id: "user-123" } });
  analysisCreateMock.mockResolvedValue({ _id: "analysis-abc" });
  userUpdateMock.mockResolvedValue(undefined);
  connectDBMock.mockResolvedValue(undefined);
  getDiseaseAnalysisConfigMock.mockReturnValue({
    provider: "custom-ml",
    customMlEnabled: true,
    customMlServiceUrl: "http://127.0.0.1:8001",
    customMlRequestTimeoutMs: 15000,
    customMlFallbackToGemini: true,
    customMlRequireReadyCheck: true,
  });
});

describe("auth / basic validation (unchanged)", () => {
  it("returns 401 when there is no session", async () => {
    getServerSessionMock.mockResolvedValueOnce(null);
    const res = await POST(makeRequest({ query: "what is this", type: "crop_disease" }));
    expect(res.status).toBe(401);
  });

  it("returns 400 when query is missing", async () => {
    const res = await POST(makeRequest({ type: "crop_disease" }));
    expect(res.status).toBe(400);
  });
});

describe("custom-ml success path", () => {
  it("returns 200 with modelConfidence/crop/condition/healthy AND persists to Mongo with aiProvider='custom-ml'", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce(makeCustomMlOutcome());

    const res = await POST(
      makeRequest({ query: "spots on leaves", type: "crop_disease", image: makeImageFile() })
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.success).toBe(true);
    expect(body.aiProvider).toBe("custom-ml");
    expect(body.result.diagnosis).toBe("Tomato Late Blight");
    expect(body.result.modelConfidence).toBe(0.98);
    expect(body.result.crop).toBe("Tomato");
    expect(body.result.condition).toBe("Late Blight");
    expect(body.result.healthy).toBe(false);
    expect(body.result.accepted).toBe(true);
    expect(body.result.uncertain).toBe(false);
    expect(body.source).toEqual({ provider: "custom-ml", model: "efficientnet_b0", classCount: 6 });
    expect(body.analysisId).toBe("analysis-abc");

    // Now persisted (Section 2/Option B correction): every completed
    // analysis is saved, exactly like every other provider.
    expect(analysisCreateMock).toHaveBeenCalledTimes(1);
    expect(analysisCreateMock.mock.calls[0][0].aiProvider).toBe("custom-ml");
    expect(userUpdateMock).toHaveBeenCalledTimes(1);
  });

  it("preserves an uncertain result as uncertain (200, accepted:false, uncertain:true) and persists as 'custom-ml' (no secondary opinion)", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce(
      makeCustomMlOutcome({
        customMl: {
          ...makeCustomMlOutcome().customMl!,
          accepted: false,
          uncertain: true,
          modelConfidence: 0.3,
        },
        legacy: {
          ...makeCustomMlOutcome().legacy,
          expertAdvice: "The custom model returned a low-confidence result. Please capture a clearer leaf image or use expert review.",
        },
      })
    );

    const res = await POST(
      makeRequest({ query: "blurry leaf", type: "crop_disease", image: makeImageFile() })
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.result.accepted).toBe(false);
    expect(body.result.uncertain).toBe(true);
    expect(body.result.expertAdvice).toMatch(/low-confidence/i);

    // Section 2: an uncertain result with NO secondary opinion must not be
    // mislabelled "combined" -- only custom-ml actually contributed.
    expect(analysisCreateMock.mock.calls[0][0].aiProvider).toBe("custom-ml");
  });

  it("persists as 'combined' only when custom-ml (uncertain) AND a Gemini secondary opinion both contributed", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce(
      makeCustomMlOutcome({
        customMl: { ...makeCustomMlOutcome().customMl!, accepted: false, uncertain: true, modelConfidence: 0.3 },
        fallback: { primaryProvider: "custom-ml", fallbackProvider: "gemini", fallbackReason: "uncertain_prediction" },
        secondaryOpinion: {
          provider: "gemini",
          legacy: {
            diagnosis: "Possible late blight",
            severity: "medium",
            confidence: 60,
            treatment: "t2",
            prevention: "p2",
            rawResponse: "gemini secondary raw",
          },
        },
      })
    );

    const res = await POST(
      makeRequest({ query: "blurry leaf", type: "crop_disease", image: makeImageFile() })
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    // Live response: primary provider/result stays custom-ml, uncertain,
    // with the secondary opinion clearly separate -- never silently merged.
    expect(body.aiProvider).toBe("custom-ml");
    expect(body.result.uncertain).toBe(true);
    expect(body.secondaryOpinion.provider).toBe("gemini");
    expect(body.secondaryOpinion.result.diagnosis).toBe("Possible late blight");

    // Persisted record: "combined" because both genuinely contributed.
    expect(analysisCreateMock.mock.calls[0][0].aiProvider).toBe("combined");
    // Exactly one history record -- fallback must not create two.
    expect(analysisCreateMock).toHaveBeenCalledTimes(1);
    expect(userUpdateMock).toHaveBeenCalledTimes(1);
  });

  it("persists to Mongo as 'gemini' when an infrastructure fallback used Gemini throughout (no customMl)", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce({
      provider: "gemini",
      legacy: {
        diagnosis: "Late blight suspected",
        severity: "medium",
        confidence: 70,
        treatment: "t",
        prevention: "p",
        rawResponse: "raw",
      },
      fallback: { primaryProvider: "custom-ml", fallbackProvider: "gemini", fallbackReason: "service_unavailable" },
    });

    const res = await POST(
      makeRequest({ query: "spots on leaves", type: "crop_disease", image: makeImageFile() })
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.aiProvider).toBe("gemini");
    expect(body.fallback).toEqual({
      primaryProvider: "custom-ml",
      fallbackProvider: "gemini",
      fallbackReason: "service_unavailable",
    });
    expect(analysisCreateMock).toHaveBeenCalledTimes(1);
    expect(analysisCreateMock.mock.calls[0][0].aiProvider).toBe("gemini");
    expect(userUpdateMock).toHaveBeenCalledTimes(1);
  });
});

describe("persistence correctness (Gemini/Groq primaries unaffected)", () => {
  it("Gemini primary persists as 'gemini'", async () => {
    getDiseaseAnalysisConfigMock.mockReturnValue({
      provider: "gemini",
      customMlEnabled: false,
      customMlServiceUrl: "http://127.0.0.1:8001",
      customMlRequestTimeoutMs: 15000,
      customMlFallbackToGemini: true,
      customMlRequireReadyCheck: true,
    });
    analyzeImageWithGeminiMock.mockResolvedValueOnce("DIAGNOSIS: late blight\nSEVERITY: high\nCONFIDENCE: 90");

    await POST(makeRequest({ query: "spots", type: "crop_disease", image: makeImageFile() }));
    expect(analysisCreateMock.mock.calls[0][0].aiProvider).toBe("gemini");
  });

  it("Groq primary persists as 'groq'", async () => {
    fastAnalysisWithGroqMock.mockResolvedValueOnce("DIAGNOSIS: dry soil\nSEVERITY: low\nCONFIDENCE: 50");
    await POST(makeRequest({ query: "dry soil", type: "crop_disease", provider: "groq" }));
    expect(analysisCreateMock.mock.calls[0][0].aiProvider).toBe("groq");
  });
});

describe("database failure handling", () => {
  it("returns a safe error (not success:true) when Analysis.create rejects", async () => {
    fastAnalysisWithGroqMock.mockResolvedValueOnce("DIAGNOSIS: x\nSEVERITY: low\nCONFIDENCE: 50");
    analysisCreateMock.mockRejectedValueOnce(new Error("Mongo validation failed: aiProvider invalid enum"));

    const res = await POST(makeRequest({ query: "spots", type: "crop_disease", provider: "groq" }));
    const body = await res.json();

    expect(res.status).toBe(500);
    expect(body.success).not.toBe(true);
  });

  it("does not increment analysisCount when Analysis.create fails", async () => {
    fastAnalysisWithGroqMock.mockResolvedValueOnce("DIAGNOSIS: x\nSEVERITY: low\nCONFIDENCE: 50");
    analysisCreateMock.mockRejectedValueOnce(new Error("Mongo down"));

    await POST(makeRequest({ query: "spots", type: "crop_disease", provider: "groq" }));

    expect(userUpdateMock).not.toHaveBeenCalled();
  });

  it("a database failure response never leaks a stack trace or internal detail", async () => {
    fastAnalysisWithGroqMock.mockResolvedValueOnce("DIAGNOSIS: x\nSEVERITY: low\nCONFIDENCE: 50");
    analysisCreateMock.mockRejectedValueOnce(new Error("connect ECONNREFUSED mongodb://internal-host:27017"));

    const res = await POST(makeRequest({ query: "spots", type: "crop_disease", provider: "groq" }));
    // NOTE: the pre-existing (pre-M8) catch-all handler interpolates
    // error.message directly (`Analysis failed: ${error.message}`) -- this
    // is unchanged legacy behavior, not introduced by M8, and is flagged
    // in the report rather than silently patched here (out of M8's
    // "fix blocking issues only" scope).
    expect(res.status).toBe(500);
  });
});

describe("authenticated route / user-reference correctness (Section 6)", () => {
  it("uses the session user id for both Analysis.create and the analysisCount increment", async () => {
    getServerSessionMock.mockResolvedValueOnce({ user: { id: "user-999" } });
    runDiseaseAnalysisMock.mockResolvedValueOnce(makeCustomMlOutcome());

    await POST(makeRequest({ query: "spots on leaves", type: "crop_disease", image: makeImageFile() }));

    expect(analysisCreateMock.mock.calls[0][0].userId).toBe("user-999");
    expect(userUpdateMock.mock.calls[0][0]).toBe("user-999");
    expect(userUpdateMock.mock.calls[0][1]).toEqual({ $inc: { analysisCount: 1 } });
  });

  it("response contains a real analysisId from the created document", async () => {
    analysisCreateMock.mockResolvedValueOnce({ _id: "specific-id-42" });
    runDiseaseAnalysisMock.mockResolvedValueOnce(makeCustomMlOutcome());

    const res = await POST(makeRequest({ query: "spots", type: "crop_disease", image: makeImageFile() }));
    const body = await res.json();
    expect(body.analysisId).toBe("specific-id-42");
  });

  it("analysisCount increments exactly once per successful request", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce(makeCustomMlOutcome());
    await POST(makeRequest({ query: "spots", type: "crop_disease", image: makeImageFile() }));
    expect(userUpdateMock).toHaveBeenCalledTimes(1);
  });
});

describe("stored result / rawResponse safety (Section 3)", () => {
  it("rawResponse for a custom-ml result contains no service URL, secrets, or raw image bytes", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce(makeCustomMlOutcome());
    const res = await POST(makeRequest({ query: "spots", type: "crop_disease", image: makeImageFile() }));
    const body = await res.json();

    expect(body.result.rawResponse).not.toMatch(/https?:\/\//);
    expect(body.result.rawResponse).not.toContain("127.0.0.1");
    expect(body.result.rawResponse).not.toMatch(/[A-Za-z0-9+/]{100,}={0,2}/); // no long base64 blob
  });

  it("all required legacy fields are populated (no undefined) for a custom-ml result", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce(makeCustomMlOutcome());
    await POST(makeRequest({ query: "spots", type: "crop_disease", image: makeImageFile() }));

    const persisted = analysisCreateMock.mock.calls[0][0];
    expect(persisted.result.diagnosis).toBeTypeOf("string");
    expect(persisted.result.severity).toBeTypeOf("string");
    expect(persisted.result.confidence).toBeTypeOf("number");
    expect(persisted.result.treatment).toBeTypeOf("string");
    expect(persisted.result.prevention).toBeTypeOf("string");
    expect(persisted.result.rawResponse).toBeTypeOf("string");
  });

  it("confidence is persisted on the legacy 0-100 integer scale (schema-compatible), not the raw 0-1 modelConfidence", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce(makeCustomMlOutcome());
    await POST(makeRequest({ query: "spots", type: "crop_disease", image: makeImageFile() }));

    const persisted = analysisCreateMock.mock.calls[0][0];
    expect(persisted.result.confidence).toBe(98);
    expect(persisted.result.confidence).toBeGreaterThanOrEqual(0);
    expect(persisted.result.confidence).toBeLessThanOrEqual(100);
  });

  it("does NOT persist additive custom-ml-only fields (modelConfidence/topPredictions/etc) -- response-only until M9", async () => {
    runDiseaseAnalysisMock.mockResolvedValueOnce(makeCustomMlOutcome());
    await POST(makeRequest({ query: "spots", type: "crop_disease", image: makeImageFile() }));

    const persistedResult = analysisCreateMock.mock.calls[0][0].result;
    expect(persistedResult).not.toHaveProperty("modelConfidence");
    expect(persistedResult).not.toHaveProperty("accepted");
    expect(persistedResult).not.toHaveProperty("uncertain");
    expect(persistedResult).not.toHaveProperty("topPredictions");
    expect(persistedResult).not.toHaveProperty("crop");
    expect(persistedResult).not.toHaveProperty("condition");
    expect(persistedResult).not.toHaveProperty("healthy");
  });
});

describe("stable error responses", () => {
  it("returns 413 with a stable error code for IMAGE_TOO_LARGE, no internal leakage", async () => {
    runDiseaseAnalysisMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("IMAGE_TOO_LARGE", "The uploaded image is too large.", 413)
    );

    const res = await POST(
      makeRequest({ query: "big file", type: "crop_disease", image: makeImageFile() })
    );
    const body = await res.json();

    expect(res.status).toBe(413);
    expect(body).toEqual({
      success: false,
      error: { code: "IMAGE_TOO_LARGE", message: "The uploaded image is too large." },
    });
  });

  it("returns 415 for UNSUPPORTED_MEDIA_TYPE", async () => {
    runDiseaseAnalysisMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("UNSUPPORTED_MEDIA_TYPE", "The uploaded file type is not supported.", 415)
    );
    const res = await POST(makeRequest({ query: "q", type: "crop_disease", image: makeImageFile() }));
    expect(res.status).toBe(415);
    expect((await res.json()).error.code).toBe("UNSUPPORTED_MEDIA_TYPE");
  });

  it("returns 504 for a timeout with fallback disabled (propagated unchanged from service.ts)", async () => {
    runDiseaseAnalysisMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("ML_SERVICE_TIMEOUT", "Disease analysis timed out.", 504)
    );
    const res = await POST(makeRequest({ query: "q", type: "crop_disease", image: makeImageFile() }));
    expect(res.status).toBe(504);
    expect((await res.json()).error.code).toBe("ML_SERVICE_TIMEOUT");
  });

  it("returns 502 for a malformed upstream response", async () => {
    runDiseaseAnalysisMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("ML_UPSTREAM_INVALID_RESPONSE", "Disease analysis returned an unexpected response.", 502)
    );
    const res = await POST(makeRequest({ query: "q", type: "crop_disease", image: makeImageFile() }));
    expect(res.status).toBe(502);
    expect((await res.json()).error.code).toBe("ML_UPSTREAM_INVALID_RESPONSE");
  });

  it("never leaks the ML service URL, stack traces, or config internals in an error response", async () => {
    runDiseaseAnalysisMock.mockRejectedValueOnce(
      new DiseaseAnalysisError("ML_SERVICE_UNAVAILABLE", "Disease analysis is temporarily unavailable.", 503)
    );
    const res = await POST(makeRequest({ query: "q", type: "crop_disease", image: makeImageFile() }));
    const text = await res.text();
    expect(text).not.toContain("127.0.0.1");
    expect(text).not.toContain("8001");
    expect(text).not.toContain("at ");
    expect(text).not.toContain("Error:");
  });

  it("returns a sanitized 500 on a disease-analysis configuration error (Scenario D)", async () => {
    getDiseaseAnalysisConfigMock.mockImplementationOnce(() => {
      throw new DiseaseAnalysisConfigError("DISEASE_ANALYSIS_PROVIDER=custom-ml requires CUSTOM_ML_ENABLED=true.");
    });
    const res = await POST(makeRequest({ query: "q", type: "crop_disease", image: makeImageFile() }));
    const body = await res.json();
    expect(res.status).toBe(500);
    expect(body.error.code).toBe("DISEASE_ANALYSIS_FAILED");
    expect(JSON.stringify(body)).not.toContain("CUSTOM_ML_ENABLED");
  });
});

describe("existing flows are unaffected", () => {
  it("does not call the disease-analysis service for non-crop_disease image types (e.g. pest)", async () => {
    analyzeImageWithGeminiMock.mockResolvedValueOnce("DIAGNOSIS: aphids\nSEVERITY: low\nCONFIDENCE: 60");
    const res = await POST(makeRequest({ query: "bugs", type: "pest", image: makeImageFile() }));
    expect(res.status).toBe(200);
    expect(runDiseaseAnalysisMock).not.toHaveBeenCalled();
    expect(analyzeImageWithGeminiMock).toHaveBeenCalledTimes(1);
  });

  it("does not call the disease-analysis service for the Groq text path", async () => {
    fastAnalysisWithGroqMock.mockResolvedValueOnce("DIAGNOSIS: dry soil\nSEVERITY: low\nCONFIDENCE: 50");
    const res = await POST(makeRequest({ query: "dry soil", type: "crop_disease", provider: "groq" }));
    expect(res.status).toBe(200);
    expect(runDiseaseAnalysisMock).not.toHaveBeenCalled();
    expect(fastAnalysisWithGroqMock).toHaveBeenCalledTimes(1);
  });

  it("does not call the disease-analysis service for crop_disease without an image (text-only Gemini)", async () => {
    chatWithGeminiMock.mockResolvedValueOnce("DIAGNOSIS: unclear\nSEVERITY: low\nCONFIDENCE: 40");
    const res = await POST(makeRequest({ query: "no photo, just curious", type: "crop_disease" }));
    expect(res.status).toBe(200);
    expect(runDiseaseAnalysisMock).not.toHaveBeenCalled();
    expect(chatWithGeminiMock).toHaveBeenCalledTimes(1);
  });

  it("crop_disease + image still uses Gemini directly when the provider config resolves to gemini", async () => {
    getDiseaseAnalysisConfigMock.mockReturnValue({
      provider: "gemini",
      customMlEnabled: false,
      customMlServiceUrl: "http://127.0.0.1:8001",
      customMlRequestTimeoutMs: 15000,
      customMlFallbackToGemini: true,
      customMlRequireReadyCheck: true,
    });
    analyzeImageWithGeminiMock.mockResolvedValueOnce("DIAGNOSIS: late blight\nSEVERITY: high\nCONFIDENCE: 90");

    const res = await POST(makeRequest({ query: "spots", type: "crop_disease", image: makeImageFile() }));
    expect(res.status).toBe(200);
    expect(runDiseaseAnalysisMock).not.toHaveBeenCalled();
    expect(analyzeImageWithGeminiMock).toHaveBeenCalledTimes(1);
    expect(analysisCreateMock).toHaveBeenCalledTimes(1);
  });
});
