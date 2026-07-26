import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DiseaseAnalysisConfigError, _resetDiseaseAnalysisConfigCacheForTests, getDiseaseAnalysisConfig } from "./config";

const ENV_KEYS = [
  "DISEASE_ANALYSIS_PROVIDER",
  "CUSTOM_ML_ENABLED",
  "CUSTOM_ML_SERVICE_URL",
  "CUSTOM_ML_REQUEST_TIMEOUT_MS",
  "CUSTOM_ML_FALLBACK_TO_GEMINI",
  "CUSTOM_ML_REQUIRE_READY_CHECK",
] as const;

let savedEnv: Record<string, string | undefined>;

beforeEach(() => {
  savedEnv = {};
  for (const key of ENV_KEYS) {
    savedEnv[key] = process.env[key];
    delete process.env[key];
  }
  _resetDiseaseAnalysisConfigCacheForTests();
});

afterEach(() => {
  for (const key of ENV_KEYS) {
    if (savedEnv[key] === undefined) delete process.env[key];
    else process.env[key] = savedEnv[key];
  }
  _resetDiseaseAnalysisConfigCacheForTests();
});

describe("getDiseaseAnalysisConfig defaults", () => {
  it("defaults to gemini, custom-ml disabled, and the documented safe defaults", () => {
    const config = getDiseaseAnalysisConfig();
    expect(config).toEqual({
      provider: "gemini",
      customMlEnabled: false,
      customMlServiceUrl: "http://127.0.0.1:8001",
      customMlRequestTimeoutMs: 15000,
      customMlFallbackToGemini: true,
      customMlRequireReadyCheck: true,
    });
  });

  it("caches the config across repeated calls", () => {
    const a = getDiseaseAnalysisConfig();
    const b = getDiseaseAnalysisConfig();
    expect(a).toBe(b);
  });
});

describe("provider validation", () => {
  it("accepts custom-ml when CUSTOM_ML_ENABLED=true", () => {
    process.env.DISEASE_ANALYSIS_PROVIDER = "custom-ml";
    process.env.CUSTOM_ML_ENABLED = "true";
    expect(getDiseaseAnalysisConfig().provider).toBe("custom-ml");
  });

  it("Scenario D: rejects custom-ml when CUSTOM_ML_ENABLED is not set (defaults false) -- fails loudly, never silently", () => {
    process.env.DISEASE_ANALYSIS_PROVIDER = "custom-ml";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });

  it("Scenario D: rejects custom-ml when CUSTOM_ML_ENABLED=false explicitly", () => {
    process.env.DISEASE_ANALYSIS_PROVIDER = "custom-ml";
    process.env.CUSTOM_ML_ENABLED = "false";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });

  it("rejects an unsupported provider value", () => {
    process.env.DISEASE_ANALYSIS_PROVIDER = "openai";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });

  it("allows CUSTOM_ML_ENABLED=true while provider stays gemini", () => {
    process.env.CUSTOM_ML_ENABLED = "true";
    process.env.DISEASE_ANALYSIS_PROVIDER = "gemini";
    const config = getDiseaseAnalysisConfig();
    expect(config.provider).toBe("gemini");
    expect(config.customMlEnabled).toBe(true);
  });
});

describe("boolean parsing", () => {
  it.each(["true", "1", "yes", "TRUE", "Yes"])("parses %s as true", (value) => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = value;
    expect(getDiseaseAnalysisConfig().customMlFallbackToGemini).toBe(true);
  });

  it.each(["false", "0", "no", "FALSE"])("parses %s as false", (value) => {
    process.env.CUSTOM_ML_FALLBACK_TO_GEMINI = value;
    expect(getDiseaseAnalysisConfig().customMlFallbackToGemini).toBe(false);
  });

  it("rejects an invalid boolean string", () => {
    process.env.CUSTOM_ML_REQUIRE_READY_CHECK = "maybe";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });
});

describe("URL validation", () => {
  it("accepts a valid http URL", () => {
    process.env.CUSTOM_ML_SERVICE_URL = "http://localhost:9000";
    expect(getDiseaseAnalysisConfig().customMlServiceUrl).toBe("http://localhost:9000");
  });

  it("strips a trailing slash", () => {
    process.env.CUSTOM_ML_SERVICE_URL = "http://localhost:9000/";
    expect(getDiseaseAnalysisConfig().customMlServiceUrl).toBe("http://localhost:9000");
  });

  it("rejects a malformed URL", () => {
    process.env.CUSTOM_ML_SERVICE_URL = "not-a-url";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });

  it("rejects a non-http(s) protocol", () => {
    process.env.CUSTOM_ML_SERVICE_URL = "ftp://localhost:9000";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });
});

describe("timeout validation", () => {
  it("accepts an in-range timeout", () => {
    process.env.CUSTOM_ML_REQUEST_TIMEOUT_MS = "20000";
    expect(getDiseaseAnalysisConfig().customMlRequestTimeoutMs).toBe(20000);
  });

  it("rejects a timeout below 1000ms", () => {
    process.env.CUSTOM_ML_REQUEST_TIMEOUT_MS = "500";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });

  it("rejects a timeout above 120000ms", () => {
    process.env.CUSTOM_ML_REQUEST_TIMEOUT_MS = "999999";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });

  it("rejects a non-numeric timeout", () => {
    process.env.CUSTOM_ML_REQUEST_TIMEOUT_MS = "soon";
    expect(() => getDiseaseAnalysisConfig()).toThrow(DiseaseAnalysisConfigError);
  });
});
