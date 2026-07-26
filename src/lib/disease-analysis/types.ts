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

/** The persisted `Analysis.aiProvider` value can additionally be "groq" or
 * "combined" (custom-ml + a Gemini secondary opinion, both contributing).
 * Kept separate from DiseaseAnalysisProvider (which only ever describes a
 * disease-analysis *provider call*, never a persistence-only label). */
export type PersistedProvider = "gemini" | "groq" | "custom-ml" | "combined";

/** The only confidence method ml-service currently supports/returns. A
 * union of one, not a bare string, so a typo or future new method is a
 * type error at every call site rather than silently accepted. */
export type ConfidenceMethod = "maximum_softmax_probability";

export const CUSTOM_ML_MODEL_INFO = {
  architecture: "efficientnet_b0",
  classCount: APPROVED_CLASS_NAMES.length,
} as const;

export interface TopPrediction {
  className: ApprovedClassName;
  classIndex: number;
  modelConfidence: number;
}

/** Structured breakdown of an approved class name -- see class-mapping.ts. */
export interface ClassBreakdown {
  crop: "Tomato" | "Potato";
  condition: string;
  healthy: boolean;
}

/** The custom-ml provider's normalized result shape (Section 6 of the M8
 * spec; extended in M9 with classIndex/confidenceThreshold/
 * confidenceMethod/model for persistence -- Section 3). Only ever produced
 * from a validated upstream response -- see providers/custom-ml.ts's
 * `validateAndNormalize`. */
export interface CustomMlNormalizedResult extends ClassBreakdown {
  disease: ApprovedClassName;
  classIndex: number;
  modelConfidence: number;
  accepted: boolean;
  uncertain: boolean;
  confidenceLabel: "model confidence";
  productionCalibrated: false;
  supportedClass: true;
  confidenceThreshold: 0.5;
  confidenceMethod: ConfidenceMethod;
  topPredictions: TopPrediction[];
  model: typeof CUSTOM_ML_MODEL_INFO;
  limitations: string[];
}

export type FallbackReason =
  | "service_unavailable"
  | "timeout"
  | "malformed_upstream"
  | "service_not_ready"
  | "uncertain_prediction";

export interface FallbackInfo {
  primaryProvider: DiseaseAnalysisProvider;
  fallbackProvider: DiseaseAnalysisProvider;
  fallbackReason: FallbackReason;
}

/** Milestone M9: honest, single-source-of-truth provider bookkeeping,
 * built once (see persistence.ts's `buildProviderMetadata`) and reused for
 * both the immediate API response and the persisted Analysis document, so
 * the two can never describe the request's provenance differently. */
export interface ProviderMetadata {
  primaryProvider: DiseaseAnalysisProvider;
  persistedProvider: PersistedProvider;
  fallbackUsed: boolean;
  fallbackProvider?: DiseaseAnalysisProvider;
  fallbackReason?: FallbackReason;
  secondaryOpinionUsed: boolean;
}

/** Milestone M9: a bounded, capped subset of a Gemini secondary opinion,
 * safe to persist and safe to render -- never treated as ground truth or
 * as confirmation of the primary custom-ml result. */
export interface PersistedSecondaryOpinion {
  provider: "gemini";
  diagnosis: string;
  severity: LegacyAnalysisResult["severity"];
  confidence: number;
  treatment: string;
  prevention: string;
  expertAdvice?: string;
}

/** Milestone M9: the exact shape written to `Analysis.result.customMl` and
 * returned in API responses -- built and independently re-validated at the
 * persistence boundary (see persistence.ts's `buildPersistedCustomMl`),
 * never assumed identical to whatever the upstream adapter produced.
 * `className` (not `disease`) intentionally, since it also covers the
 * healthy classes and reads correctly for both. */
export interface PersistedCustomMl {
  className: ApprovedClassName;
  classIndex: number;
  crop: "Tomato" | "Potato";
  condition: string;
  healthy: boolean;
  modelConfidence: number;
  accepted: boolean;
  uncertain: boolean;
  confidenceLabel: "model confidence";
  productionCalibrated: false;
  supportedClass: true;
  confidenceThreshold: 0.5;
  confidenceMethod: ConfidenceMethod;
  topPredictions: TopPrediction[];
  model: { architecture: string; classCount: number };
  limitations: string[];
}

/** Milestone M9: additive schema-version marker. New Analysis documents
 * are written with resultVersion=2 (customMl/providerMetadata/
 * secondaryOpinion-aware); pre-M9 documents have no resultVersion field at
 * all and are treated as version 1 by absence, never migrated in place. */
export type ResultVersion = 1 | 2;

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
