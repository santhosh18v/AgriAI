import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DiseaseAnalysisConfig } from "../config";
import { DiseaseAnalysisError } from "../types";
import { _resetReadyCacheForTests, predictWithCustomMl } from "./custom-ml";

function makeConfig(overrides: Partial<DiseaseAnalysisConfig> = {}): DiseaseAnalysisConfig {
  return {
    provider: "custom-ml",
    customMlEnabled: true,
    customMlServiceUrl: "http://ml-service.internal:8001",
    customMlRequestTimeoutMs: 15000,
    customMlFallbackToGemini: true,
    customMlRequireReadyCheck: false,
    ...overrides,
  };
}

function makeFile(name = "leaf.jpg", type = "image/jpeg"): File {
  return new File([new Uint8Array([1, 2, 3, 4])], name, { type });
}

const VALID_PREDICT_BODY = {
  status: "success",
  prediction: {
    class_name: "Tomato Late Blight",
    class_index: 2,
    model_confidence: 0.9842,
    accepted: true,
    uncertain: false,
    message: null,
  },
  top_predictions: [
    { class_name: "Tomato Late Blight", class_index: 2, model_confidence: 0.9842 },
    { class_name: "Tomato Early Blight", class_index: 1, model_confidence: 0.0107 },
  ],
  confidence_policy: {
    method: "maximum_softmax_probability",
    threshold: 0.5,
    label: "model confidence",
    production_calibrated: false,
  },
  input: { filename: "leaf.jpg", content_type: "image/jpeg", width: 256, height: 256 },
  timing_ms: { preprocessing: 1, inference: 2, total: 3 },
  limitations: ["Model confidence is not certainty or probability of truth."],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  _resetReadyCacheForTests();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("request construction", () => {
  it("sends a multipart POST with field name 'file' and preserves filename/MIME", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(VALID_PREDICT_BODY));
    const file = makeFile("mytest-leaf.png", "image/png");

    await predictWithCustomMl(makeConfig(), file);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://ml-service.internal:8001/api/predict/disease");
    expect(init.method).toBe("POST");
    const body = init.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    const sentFile = body.get("file") as File;
    expect(sentFile.name).toBe("mytest-leaf.png");
    expect(sentFile.type).toBe("image/png");
  });

  it("never includes the service URL in a thrown error message", async () => {
    fetchMock.mockRejectedValueOnce(new Error("connect ECONNREFUSED 127.0.0.1:8001"));
    try {
      await predictWithCustomMl(makeConfig(), makeFile());
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(DiseaseAnalysisError);
      expect((err as DiseaseAnalysisError).message).not.toContain("ml-service.internal");
      expect((err as DiseaseAnalysisError).message).not.toContain("8001");
    }
  });
});

describe("timeout", () => {
  it("aborts and raises ML_SERVICE_TIMEOUT when the request exceeds the configured timeout", async () => {
    fetchMock.mockImplementationOnce((_url: string, init: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => {
          const err = new Error("aborted");
          err.name = "AbortError";
          reject(err);
        });
      });
    });

    const config = makeConfig({ customMlRequestTimeoutMs: 1000 });
    await expect(predictWithCustomMl(config, makeFile())).rejects.toMatchObject({
      code: "ML_SERVICE_TIMEOUT",
      httpStatus: 504,
    });
  });
});

describe("readiness check", () => {
  it("calls GET /api/ready first when CUSTOM_ML_REQUIRE_READY_CHECK is enabled", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "ready", model_loaded: true }))
      .mockResolvedValueOnce(jsonResponse(VALID_PREDICT_BODY));

    await predictWithCustomMl(makeConfig({ customMlRequireReadyCheck: true }), makeFile());

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe("http://ml-service.internal:8001/api/ready");
    expect(fetchMock.mock.calls[1][0]).toBe("http://ml-service.internal:8001/api/predict/disease");
  });

  it("does not call /api/ready when the check is disabled", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(VALID_PREDICT_BODY));
    await predictWithCustomMl(makeConfig({ customMlRequireReadyCheck: false }), makeFile());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("fails safely with ML_SERVICE_NOT_READY when readiness reports not ready, without calling predict", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "not_ready", model_loaded: false }, 503));
    await expect(
      predictWithCustomMl(makeConfig({ customMlRequireReadyCheck: true }), makeFile())
    ).rejects.toMatchObject({ code: "ML_SERVICE_NOT_READY" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("valid response parsing", () => {
  it("parses a valid response into the normalized shape", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(VALID_PREDICT_BODY));
    const result = await predictWithCustomMl(makeConfig(), makeFile());

    expect(result.disease).toBe("Tomato Late Blight");
    expect(result.crop).toBe("Tomato");
    expect(result.condition).toBe("Late Blight");
    expect(result.healthy).toBe(false);
    expect(result.modelConfidence).toBe(0.9842);
    expect(result.accepted).toBe(true);
    expect(result.uncertain).toBe(false);
    expect(result.confidenceLabel).toBe("model confidence");
    expect(result.productionCalibrated).toBe(false);
    expect(result.supportedClass).toBe(true);
    expect(result.topPredictions).toHaveLength(2);
  });
});

describe("strict upstream validation", () => {
  async function expectInvalidResponse(body: unknown) {
    fetchMock.mockResolvedValueOnce(jsonResponse(body));
    await expect(predictWithCustomMl(makeConfig(), makeFile())).rejects.toMatchObject({
      code: "ML_UPSTREAM_INVALID_RESPONSE",
      httpStatus: 502,
    });
  }

  it("rejects an unknown/unsupported class name (e.g. Corn)", async () => {
    await expectInvalidResponse({
      ...VALID_PREDICT_BODY,
      prediction: { ...VALID_PREDICT_BODY.prediction, class_name: "Corn Common Rust" },
    });
  });

  it("rejects an out-of-range confidence", async () => {
    await expectInvalidResponse({
      ...VALID_PREDICT_BODY,
      prediction: { ...VALID_PREDICT_BODY.prediction, model_confidence: 1.5 },
    });
  });

  it("rejects a negative confidence", async () => {
    await expectInvalidResponse({
      ...VALID_PREDICT_BODY,
      prediction: { ...VALID_PREDICT_BODY.prediction, model_confidence: -0.1 },
    });
  });

  it("rejects a threshold other than 0.50", async () => {
    await expectInvalidResponse({
      ...VALID_PREDICT_BODY,
      confidence_policy: { ...VALID_PREDICT_BODY.confidence_policy, threshold: 0.6 },
    });
  });

  it("rejects a confidence label other than 'model confidence'", async () => {
    await expectInvalidResponse({
      ...VALID_PREDICT_BODY,
      confidence_policy: { ...VALID_PREDICT_BODY.confidence_policy, label: "certainty" },
    });
  });

  it("rejects production_calibrated=true", async () => {
    await expectInvalidResponse({
      ...VALID_PREDICT_BODY,
      confidence_policy: { ...VALID_PREDICT_BODY.confidence_policy, production_calibrated: true },
    });
  });

  it("rejects accepted/uncertain both true (not logical opposites)", async () => {
    await expectInvalidResponse({
      ...VALID_PREDICT_BODY,
      prediction: { ...VALID_PREDICT_BODY.prediction, accepted: true, uncertain: true },
    });
  });

  it("rejects accepted/uncertain both false (not logical opposites)", async () => {
    await expectInvalidResponse({
      ...VALID_PREDICT_BODY,
      prediction: { ...VALID_PREDICT_BODY.prediction, accepted: false, uncertain: false },
    });
  });

  it("rejects a non-success status", async () => {
    await expectInvalidResponse({ ...VALID_PREDICT_BODY, status: "error" });
  });

  it("rejects malformed JSON", async () => {
    fetchMock.mockResolvedValueOnce(new Response("not json", { status: 200 }));
    await expect(predictWithCustomMl(makeConfig(), makeFile())).rejects.toMatchObject({
      code: "ML_UPSTREAM_INVALID_RESPONSE",
    });
  });
});

describe("upstream HTTP status handling", () => {
  it("maps 400 to INVALID_IMAGE", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "error", detail: "bad" }, 400));
    await expect(predictWithCustomMl(makeConfig(), makeFile())).rejects.toMatchObject({
      code: "INVALID_IMAGE",
      httpStatus: 400,
    });
  });

  it("maps 413 to IMAGE_TOO_LARGE", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "error", detail: "too big" }, 413));
    await expect(predictWithCustomMl(makeConfig(), makeFile())).rejects.toMatchObject({
      code: "IMAGE_TOO_LARGE",
      httpStatus: 413,
    });
  });

  it("maps 415 to UNSUPPORTED_MEDIA_TYPE", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "error", detail: "bad type" }, 415));
    await expect(predictWithCustomMl(makeConfig(), makeFile())).rejects.toMatchObject({
      code: "UNSUPPORTED_MEDIA_TYPE",
      httpStatus: 415,
    });
  });

  it("maps 503 to ML_SERVICE_NOT_READY", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "error", detail: "not ready" }, 503));
    await expect(predictWithCustomMl(makeConfig(), makeFile())).rejects.toMatchObject({
      code: "ML_SERVICE_NOT_READY",
      httpStatus: 503,
    });
  });

  it("maps 500 to ML_SERVICE_UNAVAILABLE", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ status: "error", detail: "boom" }, 500));
    await expect(predictWithCustomMl(makeConfig(), makeFile())).rejects.toMatchObject({
      code: "ML_SERVICE_UNAVAILABLE",
      httpStatus: 503,
    });
  });

  it("maps a network failure (fetch rejects) to ML_SERVICE_UNAVAILABLE", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"));
    await expect(predictWithCustomMl(makeConfig(), makeFile())).rejects.toMatchObject({
      code: "ML_SERVICE_UNAVAILABLE",
      httpStatus: 503,
    });
  });
});
