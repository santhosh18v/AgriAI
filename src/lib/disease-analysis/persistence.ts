/**
 * Persistence-boundary shaping and validation (Milestone M9).
 *
 * Two responsibilities, both intentionally independent of the upstream
 * provider adapters' own validation (providers/custom-ml.ts's
 * validateAndNormalize):
 *
 *  1. Build the exact shapes written to MongoDB (`PersistedCustomMl`,
 *     `ProviderMetadata`, `PersistedSecondaryOpinion`) from a single
 *     source of truth, so the immediate API response and the persisted
 *     Analysis document can never describe a request's provenance
 *     differently -- see `buildProviderMetadata`.
 *  2. Re-validate every value at the point of persistence. A malformed or
 *     inconsistent value throws `PersistenceValidationError`, which must
 *     stop route.ts before it ever calls `Analysis.create` -- never
 *     persist partially, never persist an honest-looking but wrong
 *     provider label.
 */

import { classBreakdown } from "./class-mapping";
import {
  APPROVED_CLASS_NAMES,
  ApprovedClassName,
  ConfidenceMethod,
  CustomMlNormalizedResult,
  DiseaseAnalysisOutcome,
  isApprovedClassName,
  LegacyAnalysisResult,
  PersistedCustomMl,
  PersistedProvider,
  PersistedSecondaryOpinion,
  ProviderMetadata,
  ResultVersion,
  TopPrediction,
} from "./types";

const EXPECTED_THRESHOLD = 0.5;
const SUPPORTED_CONFIDENCE_METHODS: readonly ConfidenceMethod[] = ["maximum_softmax_probability"];
const MAX_TOP_PREDICTIONS = 3;
const MAX_LIMITATIONS = 10;
const MAX_DIAGNOSIS_LENGTH = 500;
const MAX_TEXT_FIELD_LENGTH = 4000;
const VALID_SEVERITIES = new Set(["critical", "high", "medium", "low", "healthy"]);
const CURRENT_RESULT_VERSION: ResultVersion = 2;

export class PersistenceValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PersistenceValidationError";
  }
}

function fail(reason: string): never {
  throw new PersistenceValidationError(reason);
}

function expectedClassIndex(className: ApprovedClassName): number {
  return APPROVED_CLASS_NAMES.indexOf(className);
}

function capText(value: string, max: number = MAX_TEXT_FIELD_LENGTH): string {
  return value.length > max ? value.slice(0, max) : value;
}

/** Independently re-validates and re-shapes a `CustomMlNormalizedResult`
 * into the exact document shape persisted at `Analysis.result.customMl`.
 * Never trusts that the adapter's own validation was sufficient -- every
 * invariant it enforces is re-checked here from scratch. */
export function buildPersistedCustomMl(customMl: CustomMlNormalizedResult): PersistedCustomMl {
  const className = customMl.disease;
  if (!isApprovedClassName(className)) fail("customMl.disease is not an approved class name");

  const classIndex = customMl.classIndex;
  if (
    typeof classIndex !== "number" ||
    !Number.isInteger(classIndex) ||
    classIndex !== expectedClassIndex(className)
  ) {
    fail("customMl.classIndex does not match the approved class ordering");
  }

  const modelConfidence = customMl.modelConfidence;
  if (
    typeof modelConfidence !== "number" ||
    !Number.isFinite(modelConfidence) ||
    modelConfidence < 0 ||
    modelConfidence > 1
  ) {
    fail("customMl.modelConfidence is out of range");
  }

  if (
    typeof customMl.accepted !== "boolean" ||
    typeof customMl.uncertain !== "boolean" ||
    customMl.accepted === customMl.uncertain
  ) {
    fail("customMl.accepted/uncertain must be strict logical opposites");
  }

  if (customMl.confidenceThreshold !== EXPECTED_THRESHOLD) fail("customMl.confidenceThreshold must be 0.5");
  if (customMl.confidenceLabel !== "model confidence") {
    fail("customMl.confidenceLabel must be 'model confidence'");
  }
  if (customMl.productionCalibrated !== false) fail("customMl.productionCalibrated must be false");
  if (customMl.supportedClass !== true) fail("customMl.supportedClass must be true");
  if (!SUPPORTED_CONFIDENCE_METHODS.includes(customMl.confidenceMethod)) {
    fail("customMl.confidenceMethod is not a supported method");
  }

  const rawTopPredictions = Array.isArray(customMl.topPredictions) ? customMl.topPredictions : [];
  const validatedTopPredictions: TopPrediction[] = [];
  for (const p of rawTopPredictions) {
    if (
      p &&
      isApprovedClassName(p.className) &&
      typeof p.classIndex === "number" &&
      p.classIndex === expectedClassIndex(p.className) &&
      typeof p.modelConfidence === "number" &&
      p.modelConfidence >= 0 &&
      p.modelConfidence <= 1
    ) {
      validatedTopPredictions.push({
        className: p.className,
        classIndex: p.classIndex,
        modelConfidence: p.modelConfidence,
      });
    }
  }
  if (validatedTopPredictions.length === 0) {
    fail("customMl.topPredictions contained no valid entries");
  }
  const boundedTopPredictions = validatedTopPredictions.slice(0, MAX_TOP_PREDICTIONS);

  const limitations = Array.isArray(customMl.limitations)
    ? customMl.limitations.filter((l): l is string => typeof l === "string").slice(0, MAX_LIMITATIONS)
    : [];

  const breakdown = classBreakdown(className);
  if (
    breakdown.crop !== customMl.crop ||
    breakdown.condition !== customMl.condition ||
    breakdown.healthy !== customMl.healthy
  ) {
    fail("customMl crop/condition/healthy does not match the approved class breakdown");
  }

  return {
    className,
    classIndex,
    crop: breakdown.crop,
    condition: breakdown.condition,
    healthy: breakdown.healthy,
    modelConfidence,
    accepted: customMl.accepted,
    uncertain: customMl.uncertain,
    confidenceLabel: "model confidence",
    productionCalibrated: false,
    supportedClass: true,
    confidenceThreshold: EXPECTED_THRESHOLD,
    confidenceMethod: customMl.confidenceMethod,
    topPredictions: boundedTopPredictions,
    model: { architecture: customMl.model.architecture, classCount: customMl.model.classCount },
    limitations,
  };
}

/** Bounds and re-validates a Gemini secondary opinion for persistence.
 * Never treated as ground truth or as confirmation of the primary
 * custom-ml result -- callers must keep it in a clearly separate field. */
export function buildPersistedSecondaryOpinion(secondary: {
  provider: "gemini";
  legacy: LegacyAnalysisResult;
}): PersistedSecondaryOpinion {
  const { legacy } = secondary;

  if (!VALID_SEVERITIES.has(legacy.severity)) fail("secondaryOpinion.severity is not a recognized value");
  if (
    typeof legacy.confidence !== "number" ||
    !Number.isFinite(legacy.confidence) ||
    legacy.confidence < 0 ||
    legacy.confidence > 100
  ) {
    fail("secondaryOpinion.confidence is out of range");
  }
  if (typeof legacy.diagnosis !== "string" || typeof legacy.treatment !== "string" || typeof legacy.prevention !== "string") {
    fail("secondaryOpinion diagnosis/treatment/prevention must be strings");
  }

  return {
    provider: "gemini",
    diagnosis: capText(legacy.diagnosis, MAX_DIAGNOSIS_LENGTH),
    severity: legacy.severity,
    confidence: legacy.confidence,
    treatment: capText(legacy.treatment),
    prevention: capText(legacy.prevention),
    expertAdvice: legacy.expertAdvice ? capText(legacy.expertAdvice) : undefined,
  };
}

/** Single source of truth for the honest provider-provenance label. Built
 * once from a `DiseaseAnalysisOutcome` and reused for both the persisted
 * document and the immediate API response, so the two can never diverge.
 * "combined" is only ever produced when a secondary opinion genuinely
 * attached to the outcome -- never as a stand-in for a single-provider
 * result. */
export function buildProviderMetadata(outcome: DiseaseAnalysisOutcome): ProviderMetadata {
  const persistedProvider: PersistedProvider = outcome.secondaryOpinion
    ? "combined"
    : outcome.customMl
      ? "custom-ml"
      : "gemini";

  return {
    primaryProvider: outcome.provider,
    persistedProvider,
    fallbackUsed: Boolean(outcome.fallback),
    fallbackProvider: outcome.fallback?.fallbackProvider,
    fallbackReason: outcome.fallback?.fallbackReason,
    secondaryOpinionUsed: Boolean(outcome.secondaryOpinion),
  };
}

/** Independently re-validates internal consistency of a `ProviderMetadata`
 * value before it is persisted -- e.g. "combined" must always agree with
 * secondaryOpinionUsed, and fallback fields must be present together or
 * absent together. */
export function validateProviderMetadataForPersistence(metadata: ProviderMetadata): ProviderMetadata {
  if (metadata.persistedProvider === "combined" && !metadata.secondaryOpinionUsed) {
    fail("persistedProvider is 'combined' but secondaryOpinionUsed is false");
  }
  if (metadata.secondaryOpinionUsed && metadata.persistedProvider !== "combined") {
    fail("secondaryOpinionUsed is true but persistedProvider is not 'combined'");
  }
  if (metadata.fallbackUsed) {
    if (!metadata.fallbackProvider || !metadata.fallbackReason) {
      fail("fallbackUsed is true but fallbackProvider/fallbackReason is missing");
    }
  } else if (metadata.fallbackProvider || metadata.fallbackReason) {
    fail("fallbackUsed is false but fallbackProvider/fallbackReason is present");
  }
  return metadata;
}

export interface DiseaseAnalysisPersistenceInput {
  customMl?: PersistedCustomMl;
  providerMetadata: ProviderMetadata;
  secondaryOpinion?: PersistedSecondaryOpinion;
  resultVersion: ResultVersion;
}

/** Builds the complete, independently-validated persistence input for a
 * disease-analysis outcome. Throws `PersistenceValidationError` -- and
 * builds nothing -- on any inconsistency; callers (route.ts) must treat
 * that as "do not call Analysis.create, do not increment analysisCount,
 * return a sanitized error". */
export function buildDiseaseAnalysisPersistenceInput(
  outcome: DiseaseAnalysisOutcome
): DiseaseAnalysisPersistenceInput {
  const providerMetadata = validateProviderMetadataForPersistence(buildProviderMetadata(outcome));

  const customMl = outcome.customMl ? buildPersistedCustomMl(outcome.customMl) : undefined;
  const secondaryOpinion = outcome.secondaryOpinion
    ? buildPersistedSecondaryOpinion(outcome.secondaryOpinion)
    : undefined;

  const impliesCustomMl =
    providerMetadata.persistedProvider === "custom-ml" || providerMetadata.persistedProvider === "combined";
  if (Boolean(customMl) !== impliesCustomMl) {
    fail("providerMetadata.persistedProvider disagrees with customMl presence");
  }
  if (Boolean(secondaryOpinion) !== providerMetadata.secondaryOpinionUsed) {
    fail("providerMetadata.secondaryOpinionUsed disagrees with secondaryOpinion presence");
  }

  return { customMl, providerMetadata, secondaryOpinion, resultVersion: CURRENT_RESULT_VERSION };
}
