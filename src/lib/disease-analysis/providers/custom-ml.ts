/**
 * Custom ML provider adapter (Milestone M8).
 *
 * Calls the FastAPI ml-service's POST /api/predict/disease with the
 * uploaded image, and (optionally) GET /api/ready first. Every upstream
 * response is strictly validated before being trusted -- an unknown class
 * name, an out-of-range confidence, a threshold other than 0.50, or any
 * other deviation from the approved contract is treated as a malformed
 * upstream response, never silently accepted.
 *
 * This module never sends a class label or a confidence threshold to the
 * ML service, and never includes the ML service's URL in any error
 * surfaced to a caller (see DiseaseAnalysisError messages below).
 */

import { classBreakdown } from "../class-mapping";
import { DiseaseAnalysisConfig } from "../config";
import { CustomMlNormalizedResult, DiseaseAnalysisError, TopPrediction, isApprovedClassName } from "../types";

const EXPECTED_THRESHOLD = 0.5;
const READY_CACHE_TTL_MS = 5000;
const READY_CHECK_MAX_TIMEOUT_MS = 5000;

interface ReadyCacheEntry {
  ready: boolean;
  expiresAt: number;
}

// Module-level, in-memory only -- never persisted (not MongoDB, not disk).
// Resets on process restart; harmless if it doesn't survive a serverless
// cold start, since it is purely an optimization, not a correctness
// requirement (every request still enforces readiness when required).
let readyCache: ReadyCacheEntry | null = null;

/** Test-only: clears the in-memory readiness cache. */
export function _resetReadyCacheForTests(): void {
  readyCache = null;
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err: any) {
    if (err?.name === "AbortError") {
      throw new DiseaseAnalysisError("ML_SERVICE_TIMEOUT", "Disease analysis timed out.", 504);
    }
    throw new DiseaseAnalysisError("ML_SERVICE_UNAVAILABLE", "Disease analysis is temporarily unavailable.", 503);
  } finally {
    clearTimeout(timer);
  }
}

async function checkReadiness(config: DiseaseAnalysisConfig): Promise<void> {
  if (!config.customMlRequireReadyCheck) return;

  const now = Date.now();
  if (readyCache && readyCache.expiresAt > now) {
    if (!readyCache.ready) {
      throw new DiseaseAnalysisError("ML_SERVICE_NOT_READY", "Disease analysis is temporarily unavailable.", 503);
    }
    return;
  }

  const timeoutMs = Math.min(config.customMlRequestTimeoutMs, READY_CHECK_MAX_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetchWithTimeout(`${config.customMlServiceUrl}/api/ready`, { method: "GET" }, timeoutMs);
  } catch (err) {
    readyCache = { ready: false, expiresAt: now + READY_CACHE_TTL_MS };
    throw err;
  }

  let ready = false;
  if (response.status === 200) {
    try {
      const body = (await response.json()) as any;
      ready = body?.status === "ready";
    } catch {
      ready = false;
    }
  }

  readyCache = { ready, expiresAt: now + READY_CACHE_TTL_MS };
  if (!ready) {
    throw new DiseaseAnalysisError("ML_SERVICE_NOT_READY", "Disease analysis is temporarily unavailable.", 503);
  }
}

function fail(): never {
  throw new DiseaseAnalysisError(
    "ML_UPSTREAM_INVALID_RESPONSE",
    "Disease analysis returned an unexpected response.",
    502
  );
}

/** Strictly validates an upstream JSON body and normalizes it. Never
 * trusts an unknown class name, an out-of-range confidence, a threshold
 * other than 0.50, a confidence label other than "model confidence", or
 * production_calibrated !== false -- any of these fail the whole response. */
function validateAndNormalize(body: unknown): CustomMlNormalizedResult {
  if (typeof body !== "object" || body === null) fail();
  const b = body as any;

  if (b.status !== "success") fail();

  const prediction = b.prediction;
  if (typeof prediction !== "object" || prediction === null) fail();

  const className = prediction.class_name;
  if (!isApprovedClassName(className)) fail(); // never silently accept Corn or any other unknown class

  const modelConfidence = prediction.model_confidence;
  if (
    typeof modelConfidence !== "number" ||
    !Number.isFinite(modelConfidence) ||
    modelConfidence < 0 ||
    modelConfidence > 1
  ) {
    fail();
  }

  const accepted = prediction.accepted;
  const uncertain = prediction.uncertain;
  if (typeof accepted !== "boolean" || typeof uncertain !== "boolean" || accepted === uncertain) {
    fail(); // accepted/uncertain must be strict logical opposites
  }

  const policy = b.confidence_policy;
  if (typeof policy !== "object" || policy === null) fail();
  if (policy.threshold !== EXPECTED_THRESHOLD) fail();
  if (policy.label !== "model confidence") fail();
  if (policy.production_calibrated !== false) fail();

  const rawTopPredictions = Array.isArray(b.top_predictions) ? b.top_predictions : [];
  const topPredictions: TopPrediction[] = [];
  for (const item of rawTopPredictions) {
    if (
      item &&
      isApprovedClassName(item.class_name) &&
      typeof item.model_confidence === "number" &&
      item.model_confidence >= 0 &&
      item.model_confidence <= 1
    ) {
      topPredictions.push({ className: item.class_name, modelConfidence: item.model_confidence });
    }
  }
  if (topPredictions.length === 0) {
    // top_predictions is supplementary; guarantee at least the primary
    // (already-validated) prediction is present rather than failing the
    // whole response over a missing/malformed supplementary list.
    topPredictions.push({ className, modelConfidence });
  }

  const limitations = Array.isArray(b.limitations)
    ? b.limitations.filter((l: unknown): l is string => typeof l === "string")
    : [];

  return {
    disease: className,
    modelConfidence,
    accepted,
    uncertain,
    confidenceLabel: "model confidence",
    productionCalibrated: false,
    supportedClass: true,
    topPredictions,
    limitations,
    ...classBreakdown(className),
  };
}

export async function predictWithCustomMl(
  config: DiseaseAnalysisConfig,
  file: File
): Promise<CustomMlNormalizedResult> {
  await checkReadiness(config);

  const formData = new FormData();
  formData.append("file", file, file.name);

  const response = await fetchWithTimeout(
    `${config.customMlServiceUrl}/api/predict/disease`,
    { method: "POST", body: formData },
    config.customMlRequestTimeoutMs
  );

  if (response.status === 400) {
    throw new DiseaseAnalysisError("INVALID_IMAGE", "The uploaded image could not be processed.", 400);
  }
  if (response.status === 413) {
    throw new DiseaseAnalysisError("IMAGE_TOO_LARGE", "The uploaded image is too large.", 413);
  }
  if (response.status === 415) {
    throw new DiseaseAnalysisError("UNSUPPORTED_MEDIA_TYPE", "The uploaded file type is not supported.", 415);
  }
  if (response.status === 503) {
    throw new DiseaseAnalysisError("ML_SERVICE_NOT_READY", "Disease analysis is temporarily unavailable.", 503);
  }
  if (response.status >= 500) {
    throw new DiseaseAnalysisError("ML_SERVICE_UNAVAILABLE", "Disease analysis is temporarily unavailable.", 503);
  }
  if (response.status !== 200) {
    fail();
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    fail();
  }

  return validateAndNormalize(body);
}
