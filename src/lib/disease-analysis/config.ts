/**
 * Validated, server-side-only disease-analysis feature-flag configuration
 * (Milestone M8). This module never touches NEXT_PUBLIC_ variables and is
 * only ever imported from server code (API routes, provider adapters) --
 * none of these values are ever sent to the browser bundle.
 *
 * Fails fast (throws) on construction if the flag combination is
 * inconsistent (DISEASE_ANALYSIS_PROVIDER=custom-ml without
 * CUSTOM_ML_ENABLED=true) rather than silently ignoring the requested
 * provider or silently enabling custom-ml -- see Section 15, Scenario D of
 * the M8 spec.
 */

export interface DiseaseAnalysisConfig {
  provider: "custom-ml" | "gemini";
  customMlEnabled: boolean;
  customMlServiceUrl: string;
  customMlRequestTimeoutMs: number;
  customMlFallbackToGemini: boolean;
  customMlRequireReadyCheck: boolean;
}

export class DiseaseAnalysisConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DiseaseAnalysisConfigError";
  }
}

const DEFAULTS = {
  provider: "gemini" as const,
  customMlEnabled: false,
  customMlServiceUrl: "http://127.0.0.1:8001",
  customMlRequestTimeoutMs: 15000,
  customMlFallbackToGemini: true,
  customMlRequireReadyCheck: true,
};

function parseBoolean(raw: string | undefined, fallback: boolean, varName: string): boolean {
  if (raw === undefined || raw.trim() === "") return fallback;
  const normalized = raw.trim().toLowerCase();
  if (["true", "1", "yes"].includes(normalized)) return true;
  if (["false", "0", "no"].includes(normalized)) return false;
  throw new DiseaseAnalysisConfigError(
    `${varName} must be a boolean-like value (true/false/1/0/yes/no), got ${JSON.stringify(raw)}`
  );
}

function parseProvider(raw: string | undefined): "custom-ml" | "gemini" {
  const value = raw && raw.trim() !== "" ? raw.trim() : DEFAULTS.provider;
  if (value !== "custom-ml" && value !== "gemini") {
    throw new DiseaseAnalysisConfigError(
      `DISEASE_ANALYSIS_PROVIDER must be "custom-ml" or "gemini", got ${JSON.stringify(raw)}`
    );
  }
  return value;
}

function parseUrl(raw: string | undefined, varName: string): string {
  const value = raw && raw.trim() !== "" ? raw.trim() : DEFAULTS.customMlServiceUrl;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new DiseaseAnalysisConfigError(`${varName} must be a valid URL, got ${JSON.stringify(raw)}`);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new DiseaseAnalysisConfigError(`${varName} must use http:// or https://, got ${JSON.stringify(raw)}`);
  }
  return value.replace(/\/+$/, "");
}

function parseTimeoutMs(raw: string | undefined, varName: string): number {
  if (raw === undefined || raw.trim() === "") return DEFAULTS.customMlRequestTimeoutMs;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1000 || n > 120000) {
    throw new DiseaseAnalysisConfigError(
      `${varName} must be a number of milliseconds between 1000 and 120000, got ${JSON.stringify(raw)}`
    );
  }
  return n;
}

function buildConfig(): DiseaseAnalysisConfig {
  const customMlEnabled = parseBoolean(process.env.CUSTOM_ML_ENABLED, DEFAULTS.customMlEnabled, "CUSTOM_ML_ENABLED");
  const provider = parseProvider(process.env.DISEASE_ANALYSIS_PROVIDER);

  if (provider === "custom-ml" && !customMlEnabled) {
    throw new DiseaseAnalysisConfigError(
      "DISEASE_ANALYSIS_PROVIDER=custom-ml requires CUSTOM_ML_ENABLED=true. Refusing to start with an " +
        "inconsistent feature-flag configuration rather than silently ignoring the requested provider."
    );
  }

  return {
    provider,
    customMlEnabled,
    customMlServiceUrl: parseUrl(process.env.CUSTOM_ML_SERVICE_URL, "CUSTOM_ML_SERVICE_URL"),
    customMlRequestTimeoutMs: parseTimeoutMs(process.env.CUSTOM_ML_REQUEST_TIMEOUT_MS, "CUSTOM_ML_REQUEST_TIMEOUT_MS"),
    customMlFallbackToGemini: parseBoolean(
      process.env.CUSTOM_ML_FALLBACK_TO_GEMINI,
      DEFAULTS.customMlFallbackToGemini,
      "CUSTOM_ML_FALLBACK_TO_GEMINI"
    ),
    customMlRequireReadyCheck: parseBoolean(
      process.env.CUSTOM_ML_REQUIRE_READY_CHECK,
      DEFAULTS.customMlRequireReadyCheck,
      "CUSTOM_ML_REQUIRE_READY_CHECK"
    ),
  };
}

let cachedConfig: DiseaseAnalysisConfig | null = null;

export function getDiseaseAnalysisConfig(): DiseaseAnalysisConfig {
  if (!cachedConfig) {
    cachedConfig = buildConfig();
  }
  return cachedConfig;
}

/** Test-only: clears the module-level cache so a test can change
 * process.env and re-validate. Never called from application code. */
export function _resetDiseaseAnalysisConfigCacheForTests(): void {
  cachedConfig = null;
}
