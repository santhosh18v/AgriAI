import { describe, expect, it } from "vitest";

import Analysis from "./Analysis";

// Milestone M9: pure schema-validation tests. `validateSync()` runs
// entirely in memory (no MongoDB connection needed), which is enough to
// exercise Mongoose's required/enum/custom-validator rules -- the actual
// persistence path (Analysis.create) is exercised separately in
// src/app/api/analyze/route.test.ts with a mocked model.

function baseDoc(overrides: Record<string, unknown> = {}) {
  return {
    userId: "user-1",
    type: "crop_disease",
    query: "what is wrong with my tomato plant",
    aiProvider: "custom-ml",
    result: {
      diagnosis: "Tomato Late Blight",
      severity: "medium",
      confidence: 98,
      treatment: "Consult extension resources.",
      prevention: "Follow sanitation practices.",
      rawResponse: "raw",
    },
    tags: ["crop_disease"],
    ...overrides,
  };
}

function validCustomMl(overrides: Record<string, unknown> = {}) {
  return {
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
    ...overrides,
  };
}

describe("Analysis schema -- legacy compatibility", () => {
  it("validates a pre-M9-style document with no M9 fields at all", () => {
    const doc = new Analysis(baseDoc());
    const err = doc.validateSync();
    expect(err).toBeUndefined();
  });

  it("leaves customMl/providerMetadata/secondaryOpinion/resultVersion undefined rather than {} when omitted", () => {
    const doc = new Analysis(baseDoc());
    expect(doc.customMl).toBeUndefined();
    expect(doc.providerMetadata).toBeUndefined();
    expect(doc.secondaryOpinion).toBeUndefined();
    expect(doc.resultVersion).toBeUndefined();
  });

  it("validates a legacy aiProvider value ('gemini') with no M9 fields", () => {
    const doc = new Analysis(baseDoc({ aiProvider: "gemini" }));
    expect(doc.validateSync()).toBeUndefined();
  });
});

describe("Analysis schema -- customMl subdocument", () => {
  it("validates a fully-populated, valid customMl payload", () => {
    const doc = new Analysis(baseDoc({ customMl: validCustomMl(), resultVersion: 2 }));
    expect(doc.validateSync()).toBeUndefined();
  });

  it("rejects an unapproved className", () => {
    const doc = new Analysis(baseDoc({ customMl: validCustomMl({ className: "Corn Common Rust" }) }));
    expect(doc.validateSync()?.errors["customMl.className"]).toBeDefined();
  });

  it("rejects productionCalibrated=true via the custom validator", () => {
    const doc = new Analysis(baseDoc({ customMl: validCustomMl({ productionCalibrated: true }) }));
    expect(doc.validateSync()?.errors["customMl.productionCalibrated"]).toBeDefined();
  });

  it("rejects supportedClass=false via the custom validator", () => {
    const doc = new Analysis(baseDoc({ customMl: validCustomMl({ supportedClass: false }) }));
    expect(doc.validateSync()?.errors["customMl.supportedClass"]).toBeDefined();
  });

  it("rejects a confidenceThreshold other than 0.5", () => {
    const doc = new Analysis(baseDoc({ customMl: validCustomMl({ confidenceThreshold: 0.6 }) }));
    expect(doc.validateSync()?.errors["customMl.confidenceThreshold"]).toBeDefined();
  });

  it("rejects an unsupported confidenceMethod", () => {
    const doc = new Analysis(baseDoc({ customMl: validCustomMl({ confidenceMethod: "other" }) }));
    expect(doc.validateSync()?.errors["customMl.confidenceMethod"]).toBeDefined();
  });

  it("rejects a missing required field inside customMl (classIndex)", () => {
    const { classIndex, ...withoutClassIndex } = validCustomMl();
    const doc = new Analysis(baseDoc({ customMl: withoutClassIndex }));
    expect(doc.validateSync()?.errors["customMl.classIndex"]).toBeDefined();
  });
});

describe("Analysis schema -- providerMetadata subdocument", () => {
  it("validates a consistent providerMetadata payload", () => {
    const doc = new Analysis(
      baseDoc({
        providerMetadata: {
          primaryProvider: "custom-ml",
          persistedProvider: "custom-ml",
          fallbackUsed: false,
          secondaryOpinionUsed: false,
        },
      })
    );
    expect(doc.validateSync()).toBeUndefined();
  });

  it("rejects an unrecognized persistedProvider value", () => {
    const doc = new Analysis(
      baseDoc({
        providerMetadata: {
          primaryProvider: "custom-ml",
          persistedProvider: "not-a-real-provider",
          fallbackUsed: false,
          secondaryOpinionUsed: false,
        },
      })
    );
    expect(doc.validateSync()?.errors["providerMetadata.persistedProvider"]).toBeDefined();
  });
});

describe("Analysis schema -- secondaryOpinion subdocument", () => {
  it("validates a valid secondaryOpinion payload", () => {
    const doc = new Analysis(
      baseDoc({
        secondaryOpinion: {
          provider: "gemini",
          diagnosis: "Possible late blight",
          severity: "medium",
          confidence: 70,
          treatment: "Consult extension resources.",
          prevention: "Follow sanitation practices.",
        },
      })
    );
    expect(doc.validateSync()).toBeUndefined();
  });

  it("rejects an out-of-range confidence", () => {
    const doc = new Analysis(
      baseDoc({
        secondaryOpinion: {
          provider: "gemini",
          diagnosis: "Possible late blight",
          severity: "medium",
          confidence: 150,
          treatment: "Consult extension resources.",
          prevention: "Follow sanitation practices.",
        },
      })
    );
    expect(doc.validateSync()?.errors["secondaryOpinion.confidence"]).toBeDefined();
  });
});

describe("Analysis schema -- resultVersion", () => {
  it("accepts 1 and 2", () => {
    expect(new Analysis(baseDoc({ resultVersion: 1 })).validateSync()).toBeUndefined();
    expect(new Analysis(baseDoc({ resultVersion: 2 })).validateSync()).toBeUndefined();
  });

  it("rejects an unrecognized version number", () => {
    const doc = new Analysis(baseDoc({ resultVersion: 3 }));
    expect(doc.validateSync()?.errors["resultVersion"]).toBeDefined();
  });
});
