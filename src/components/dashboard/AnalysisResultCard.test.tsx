// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AnalysisResultCard } from "./AnalysisResultCard";
import { PersistedCustomMl, PersistedSecondaryOpinion, ProviderMetadata } from "@/lib/disease-analysis/types";

// vitest.config.ts does not set `test.globals: true`, so RTL's automatic
// afterEach cleanup (which relies on detecting a global `afterEach`) never
// registers -- without this, DOM from one test leaks into the next.
afterEach(() => cleanup());

function makeResult(overrides: Record<string, unknown> = {}) {
  return {
    diagnosis: "Tomato Late Blight",
    severity: "medium",
    confidence: 98,
    treatment: "Consult extension resources.",
    prevention: "Follow sanitation practices.",
    rawResponse: "raw response text",
    ...overrides,
  };
}

function makeCustomMl(overrides: Partial<PersistedCustomMl> = {}): PersistedCustomMl {
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

describe("AnalysisResultCard -- legacy rendering (no customMl)", () => {
  it("renders diagnosis, treatment, and prevention for a plain Gemini/Groq result", () => {
    render(<AnalysisResultCard result={makeResult()} aiProvider="gemini" />);
    expect(screen.getByText("Tomato Late Blight")).toBeInTheDocument();
    expect(screen.getByText("Consult extension resources.")).toBeInTheDocument();
    expect(screen.getByText("Follow sanitation practices.")).toBeInTheDocument();
    expect(screen.getByText("Gemini Vision")).toBeInTheDocument();
  });

  it("does not render any custom-ml-only UI when customMl is absent", () => {
    render(<AnalysisResultCard result={makeResult()} aiProvider="groq" />);
    expect(screen.queryByText(/Model limitations/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Predicted class/i)).not.toBeInTheDocument();
  });
});

describe("AnalysisResultCard -- accepted custom-ml result", () => {
  it("labels an accepted result 'Model prediction', never 'Confirmed disease'", () => {
    render(<AnalysisResultCard result={makeResult()} aiProvider="custom-ml" customMl={makeCustomMl()} />);
    expect(screen.getByText("Model prediction")).toBeInTheDocument();
    expect(screen.queryByText(/Confirmed disease/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Low-confidence model result/i)).not.toBeInTheDocument();
  });

  it("shows predicted class, crop/condition, model confidence, and the acceptance threshold", () => {
    render(<AnalysisResultCard result={makeResult()} aiProvider="custom-ml" customMl={makeCustomMl()} />);
    expect(screen.getByText("Predicted class")).toBeInTheDocument();
    expect(screen.getByText("Crop / condition")).toBeInTheDocument();
    expect(screen.getByText(/disease detected/)).toBeInTheDocument();
    expect(screen.getAllByText(/98%/).length).toBeGreaterThan(0);
    expect(screen.getByText(/threshold 50%/)).toBeInTheDocument();
  });

  it("shows the fixed safety-limitation wording (six-class scope, no real-world validation)", () => {
    render(<AnalysisResultCard result={makeResult()} aiProvider="custom-ml" customMl={makeCustomMl()} />);
    expect(screen.getByText(/six Tomato\/Potato classes/i)).toBeInTheDocument();
    expect(screen.getByText(/not yet been validated against real-world field conditions/i)).toBeInTheDocument();
  });
});

describe("AnalysisResultCard -- uncertain custom-ml result", () => {
  it("shows a visible low-confidence warning, never a confirmed-diagnosis message", () => {
    const uncertain = makeCustomMl({ accepted: false, uncertain: true, modelConfidence: 0.3 });
    render(<AnalysisResultCard result={makeResult()} aiProvider="custom-ml" customMl={uncertain} />);

    expect(screen.getAllByText(/Low-confidence model result/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Confirmed disease/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Model prediction")).not.toBeInTheDocument();
  });

  it("renders a secondary opinion clearly labelled as non-confirming", () => {
    const uncertain = makeCustomMl({ accepted: false, uncertain: true, modelConfidence: 0.3 });
    const secondaryOpinion: PersistedSecondaryOpinion = {
      provider: "gemini",
      diagnosis: "Possible late blight",
      severity: "medium",
      confidence: 60,
      treatment: "t2",
      prevention: "p2",
    };
    render(
      <AnalysisResultCard
        result={makeResult()}
        aiProvider="custom-ml"
        customMl={uncertain}
        secondaryOpinion={secondaryOpinion}
      />
    );

    expect(screen.getByText(/Secondary opinion \(Gemini\)/i)).toBeInTheDocument();
    expect(screen.getByText("Possible late blight")).toBeInTheDocument();
    expect(screen.getByText(/does not confirm or override/i)).toBeInTheDocument();
  });
});

describe("AnalysisResultCard -- fallback note", () => {
  it("shows a fallback note for a full infrastructure fallback (no customMl)", () => {
    const providerMetadata: ProviderMetadata = {
      primaryProvider: "gemini",
      persistedProvider: "gemini",
      fallbackUsed: true,
      fallbackProvider: "gemini",
      fallbackReason: "timeout",
      secondaryOpinionUsed: false,
    };
    render(
      <AnalysisResultCard result={makeResult()} aiProvider="gemini" providerMetadata={providerMetadata} />
    );
    expect(screen.getByText(/Fell back to Gemini Vision/i)).toBeInTheDocument();
    expect(screen.getByText(/took too long to respond/i)).toBeInTheDocument();
  });

  it("shows no fallback note when fallbackUsed is false", () => {
    const providerMetadata: ProviderMetadata = {
      primaryProvider: "custom-ml",
      persistedProvider: "custom-ml",
      fallbackUsed: false,
      secondaryOpinionUsed: false,
    };
    render(
      <AnalysisResultCard
        result={makeResult()}
        aiProvider="custom-ml"
        customMl={makeCustomMl()}
        providerMetadata={providerMetadata}
      />
    );
    expect(screen.queryByText(/Fell back to/i)).not.toBeInTheDocument();
  });
});
