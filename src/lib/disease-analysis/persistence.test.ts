import { describe, expect, it } from "vitest";

import {
  buildDiseaseAnalysisPersistenceInput,
  buildPersistedCustomMl,
  buildPersistedSecondaryOpinion,
  buildProviderMetadata,
  PersistenceValidationError,
  validateProviderMetadataForPersistence,
} from "./persistence";
import { CustomMlNormalizedResult, DiseaseAnalysisOutcome, LegacyAnalysisResult, ProviderMetadata } from "./types";

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

function makeLegacy(overrides: Partial<LegacyAnalysisResult> = {}): LegacyAnalysisResult {
  return {
    diagnosis: "Tomato Late Blight",
    severity: "medium",
    confidence: 70,
    treatment: "Consult extension resources.",
    prevention: "Follow sanitation practices.",
    rawResponse: "raw",
    ...overrides,
  };
}

function makeOutcome(overrides: Partial<DiseaseAnalysisOutcome> = {}): DiseaseAnalysisOutcome {
  return {
    provider: "custom-ml",
    legacy: makeLegacy(),
    customMl: makeCustomMlResult(),
    ...overrides,
  };
}

describe("buildPersistedCustomMl", () => {
  it("builds the persisted shape from a valid normalized result", () => {
    const persisted = buildPersistedCustomMl(makeCustomMlResult());
    expect(persisted).toEqual({
      className: "Tomato Late Blight",
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
    });
  });

  it("caps topPredictions at 3 entries", () => {
    const persisted = buildPersistedCustomMl(
      makeCustomMlResult({
        topPredictions: [
          { className: "Tomato Late Blight", classIndex: 2, modelConfidence: 0.5 },
          { className: "Tomato Early Blight", classIndex: 1, modelConfidence: 0.3 },
          { className: "Tomato Healthy", classIndex: 0, modelConfidence: 0.1 },
          { className: "Potato Healthy", classIndex: 3, modelConfidence: 0.1 },
        ],
      })
    );
    expect(persisted.topPredictions).toHaveLength(3);
  });

  it("caps limitations at 10 entries", () => {
    const persisted = buildPersistedCustomMl(
      makeCustomMlResult({ limitations: Array.from({ length: 15 }, (_, i) => `limitation ${i}`) })
    );
    expect(persisted.limitations).toHaveLength(10);
  });

  it("rejects an unapproved class name", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ disease: "Corn Common Rust" as any }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects a classIndex that disagrees with the approved ordering", () => {
    expect(() => buildPersistedCustomMl(makeCustomMlResult({ classIndex: 5 }))).toThrow(
      PersistenceValidationError
    );
  });

  it("rejects an out-of-range modelConfidence", () => {
    expect(() => buildPersistedCustomMl(makeCustomMlResult({ modelConfidence: 1.5 }))).toThrow(
      PersistenceValidationError
    );
  });

  it("rejects accepted/uncertain both true", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ accepted: true, uncertain: true }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects accepted/uncertain both false", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ accepted: false, uncertain: false }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects a confidenceThreshold other than 0.5", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ confidenceThreshold: 0.6 as any }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects a confidenceLabel other than 'model confidence'", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ confidenceLabel: "certainty" as any }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects productionCalibrated=true", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ productionCalibrated: true as any }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects supportedClass=false", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ supportedClass: false as any }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects an unsupported confidenceMethod", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ confidenceMethod: "something_else" as any }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects a crop/condition/healthy that disagrees with the approved class breakdown", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ crop: "Potato" }))
    ).toThrow(PersistenceValidationError);
  });

  it("falls back to an empty topPredictions list, then rejects, when all entries are malformed", () => {
    expect(() =>
      buildPersistedCustomMl(makeCustomMlResult({ topPredictions: [{ className: "bad" } as any] }))
    ).toThrow(PersistenceValidationError);
  });
});

describe("buildPersistedSecondaryOpinion", () => {
  it("builds the persisted shape from a valid legacy result", () => {
    const persisted = buildPersistedSecondaryOpinion({ provider: "gemini", legacy: makeLegacy() });
    expect(persisted).toEqual({
      provider: "gemini",
      diagnosis: "Tomato Late Blight",
      severity: "medium",
      confidence: 70,
      treatment: "Consult extension resources.",
      prevention: "Follow sanitation practices.",
      expertAdvice: undefined,
    });
  });

  it("caps overlong text fields", () => {
    const longText = "a".repeat(5000);
    const persisted = buildPersistedSecondaryOpinion({
      provider: "gemini",
      legacy: makeLegacy({ diagnosis: longText, treatment: longText, prevention: longText, expertAdvice: longText }),
    });
    expect(persisted.diagnosis.length).toBe(500);
    expect(persisted.treatment.length).toBe(4000);
    expect(persisted.prevention.length).toBe(4000);
    expect(persisted.expertAdvice?.length).toBe(4000);
  });

  it("rejects an unrecognized severity value", () => {
    expect(() =>
      buildPersistedSecondaryOpinion({ provider: "gemini", legacy: makeLegacy({ severity: "unknown" as any }) })
    ).toThrow(PersistenceValidationError);
  });

  it("rejects an out-of-range confidence", () => {
    expect(() =>
      buildPersistedSecondaryOpinion({ provider: "gemini", legacy: makeLegacy({ confidence: 150 }) })
    ).toThrow(PersistenceValidationError);
  });
});

describe("buildProviderMetadata", () => {
  it("labels a pure custom-ml result as 'custom-ml'", () => {
    const metadata = buildProviderMetadata(makeOutcome());
    expect(metadata.persistedProvider).toBe("custom-ml");
    expect(metadata.secondaryOpinionUsed).toBe(false);
    expect(metadata.fallbackUsed).toBe(false);
  });

  it("labels a custom-ml result with a secondary opinion as 'combined', never as single-source", () => {
    const metadata = buildProviderMetadata(
      makeOutcome({ secondaryOpinion: { provider: "gemini", legacy: makeLegacy() } })
    );
    expect(metadata.persistedProvider).toBe("combined");
    expect(metadata.secondaryOpinionUsed).toBe(true);
  });

  it("labels a full infrastructure fallback (no customMl) as 'gemini'", () => {
    const metadata = buildProviderMetadata(
      makeOutcome({
        provider: "gemini",
        customMl: undefined,
        fallback: { primaryProvider: "custom-ml", fallbackProvider: "gemini", fallbackReason: "timeout" },
      })
    );
    expect(metadata.persistedProvider).toBe("gemini");
    expect(metadata.fallbackUsed).toBe(true);
    expect(metadata.fallbackProvider).toBe("gemini");
    expect(metadata.fallbackReason).toBe("timeout");
  });
});

describe("validateProviderMetadataForPersistence", () => {
  function makeMetadata(overrides: Partial<ProviderMetadata> = {}): ProviderMetadata {
    return {
      primaryProvider: "custom-ml",
      persistedProvider: "custom-ml",
      fallbackUsed: false,
      secondaryOpinionUsed: false,
      ...overrides,
    };
  }

  it("accepts a consistent metadata value", () => {
    expect(() => validateProviderMetadataForPersistence(makeMetadata())).not.toThrow();
  });

  it("rejects 'combined' without secondaryOpinionUsed", () => {
    expect(() =>
      validateProviderMetadataForPersistence(makeMetadata({ persistedProvider: "combined" }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects secondaryOpinionUsed=true with a persistedProvider other than 'combined'", () => {
    expect(() =>
      validateProviderMetadataForPersistence(makeMetadata({ secondaryOpinionUsed: true }))
    ).toThrow(PersistenceValidationError);
  });

  it("rejects fallbackUsed=true with a missing fallbackProvider/fallbackReason", () => {
    expect(() => validateProviderMetadataForPersistence(makeMetadata({ fallbackUsed: true }))).toThrow(
      PersistenceValidationError
    );
  });

  it("rejects fallbackUsed=false with a fallbackProvider present", () => {
    expect(() =>
      validateProviderMetadataForPersistence(makeMetadata({ fallbackProvider: "gemini" }))
    ).toThrow(PersistenceValidationError);
  });
});

describe("buildDiseaseAnalysisPersistenceInput", () => {
  it("builds a full, consistent persistence input for a pure custom-ml outcome", () => {
    const input = buildDiseaseAnalysisPersistenceInput(makeOutcome());
    expect(input.resultVersion).toBe(2);
    expect(input.customMl?.className).toBe("Tomato Late Blight");
    expect(input.secondaryOpinion).toBeUndefined();
    expect(input.providerMetadata.persistedProvider).toBe("custom-ml");
  });

  it("builds a full, consistent persistence input for a combined outcome", () => {
    const input = buildDiseaseAnalysisPersistenceInput(
      makeOutcome({ secondaryOpinion: { provider: "gemini", legacy: makeLegacy() } })
    );
    expect(input.providerMetadata.persistedProvider).toBe("combined");
    expect(input.customMl).toBeDefined();
    expect(input.secondaryOpinion).toBeDefined();
  });

  it("builds a persistence input with no customMl for a full infrastructure fallback", () => {
    const input = buildDiseaseAnalysisPersistenceInput(
      makeOutcome({
        provider: "gemini",
        customMl: undefined,
        fallback: { primaryProvider: "custom-ml", fallbackProvider: "gemini", fallbackReason: "timeout" },
      })
    );
    expect(input.customMl).toBeUndefined();
    expect(input.providerMetadata.persistedProvider).toBe("gemini");
  });

  it("throws and builds nothing when the customMl payload is invalid, even if providerMetadata would be consistent", () => {
    expect(() =>
      buildDiseaseAnalysisPersistenceInput(makeOutcome({ customMl: makeCustomMlResult({ modelConfidence: 5 }) }))
    ).toThrow(PersistenceValidationError);
  });
});
