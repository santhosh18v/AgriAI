/**
 * Shared disease-analysis types (Milestone M8).
 *
 * These types are used internally by the provider adapters and the
 * service orchestrator. They are deliberately NOT the final JSON shape
 * returned to the browser by `src/app/api/analyze/route.ts` -- that route
 * maps `NormalizedDiseaseResult` into the existing, UI-compatible response
 * envelope (`diagnosis`/`severity`/`confidence`/`treatment`/`prevention`/
 * `expertAdvice`/`rawResponse`) so the current frontend (M9 scope for any
 * redesign) keeps working unmodified, while also including these richer
 * fields additively for forward use.
 */

/** The six classes the custom ML model supports. Never widen this list
 * without an approved ml-service model_scope change. */
export const APPROVED_CLASS_NAMES = [
  "Tomato Healthy",
  "Tomato Early Blight",
  "Tomato Late Blight",
  "Potato Healthy",
  "Potato Early Blight",
  "Potato Late Blight",
] as const;

export type ApprovedClassName = (typeof APPROVED_CLASS_NAMES)[number];

export function isApprovedClassName(value: unknown): value is ApprovedClassName {
  return typeof value === "string" && (APPROVED_CLASS_NAMES as readonly string[]).includes(value);
}

export type DiseaseAnalysisProvider = "custom-ml" | "gemini";

export interface TopPrediction {
  className: ApprovedClassName;
  modelConfidence: number;
}

/** Structured breakdown of an approved class name -- see class-mapping.ts. */
export interface ClassBreakdown {
  crop: "Tomato" | "Potato";
  condition: string;
  healthy: boolean;
}

/** The custom-ml provider's normalized result shape (Section 6 of the M8
 * spec). Only ever produced from a validated upstream response -- see
 * providers/custom-ml.ts's `validateUpstreamResponse`. */
export interface CustomMlNormalizedResult extends ClassBreakdown {
  disease: ApprovedClassName;
  modelConfidence: number;
  accepted: boolean;
  uncertain: boolean;
  confidenceLabel: "model confidence";
  productionCalibrated: false;
  supportedClass: true;
  topPredictions: TopPrediction[];
  limitations: string[];
}

export type FallbackReason =
  | "service_unavailable"
  | "timeout"
  | "malformed_upstream"
  | "not_ready"
  | "uncertain_prediction";

export interface FallbackInfo {
  primaryProvider: DiseaseAnalysisProvider;
  fallbackProvider: DiseaseAnalysisProvider;
  fallbackReason: FallbackReason;
}

/** The legacy, UI-compatible result shape already produced by the Gemini
 * text-parsing path (see providers/gemini.ts's parseAIResponse, moved
 * unchanged from the original route.ts). */
export interface LegacyAnalysisResult {
  diagnosis: string;
  severity: "critical" | "high" | "medium" | "low" | "healthy";
  confidence: number; // 0-100 integer, legacy scale
  treatment: string;
  prevention: string;
  expertAdvice?: string;
  rawResponse: string;
}

/** What service.ts returns to route.ts: the legacy shape (so the existing
 * response envelope keeps working unchanged) plus optional custom-ml-only
 * enrichment fields and fallback metadata. */
export interface DiseaseAnalysisOutcome {
  provider: DiseaseAnalysisProvider;
  legacy: LegacyAnalysisResult;
  customMl?: CustomMlNormalizedResult;
  fallback?: FallbackInfo;
  /** Only set for an uncertain custom-ml result where Gemini was
   * additionally consulted as a secondary opinion (Section 7 of the M8
   * spec) -- never replaces `legacy`/`customMl`, which stay the primary,
   * uncertain custom-ml result. Labelled separately so the client can
   * never mistake this for confirmation of the primary result. */
  secondaryOpinion?: {
    provider: "gemini";
    legacy: LegacyAnalysisResult;
  };
}

export class DiseaseAnalysisError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly httpStatus: number
  ) {
    super(message);
    this.name = "DiseaseAnalysisError";
  }
}
