// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HistoryList } from "./HistoryList";

// vitest.config.ts does not set `test.globals: true`, so RTL's automatic
// afterEach cleanup never registers -- without this, DOM from one test
// leaks into the next.
afterEach(() => cleanup());

const fetchMock = vi.fn();

function jsonResponse(body: unknown) {
  return Promise.resolve({ json: () => Promise.resolve(body) } as Response);
}

function legacyEntry(overrides: Record<string, unknown> = {}) {
  return {
    id: "legacy-1",
    type: "crop_disease",
    query: "old scan",
    diagnosis: "Healthy",
    severity: "healthy",
    confidence: 80,
    treatment: "None needed.",
    prevention: "Keep monitoring.",
    aiProvider: "gemini",
    createdAt: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

function customMlEntry(overrides: Record<string, unknown> = {}) {
  return {
    id: "cm-1",
    type: "crop_disease",
    query: "spots on leaves",
    diagnosis: "Tomato Late Blight",
    severity: "medium",
    confidence: 98,
    treatment: "Consult extension resources.",
    prevention: "Follow sanitation practices.",
    cropName: "Tomato",
    aiProvider: "custom-ml",
    resultVersion: 2,
    customMl: {
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
    },
    providerMetadata: {
      primaryProvider: "custom-ml",
      persistedProvider: "custom-ml",
      fallbackUsed: false,
      secondaryOpinionUsed: false,
    },
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HistoryList", () => {
  it("renders a legacy record (no customMl) without crashing", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ analyses: [legacyEntry()] }));
    render(<HistoryList />);

    expect(await screen.findByText("Healthy")).toBeInTheDocument();
    expect(screen.getByText("Gemini Vision")).toBeInTheDocument();
  });

  it("shows the custom-ml status badge and expands to the model-detail panel", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ analyses: [customMlEntry()] }));
    render(<HistoryList />);

    await screen.findByText("Tomato Late Blight");
    expect(screen.getByText("Model prediction")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Tomato Late Blight"));

    expect(await screen.findByText("Model confidence")).toBeInTheDocument();
    expect(screen.getByText(/six Tomato\/Potato classes/i)).toBeInTheDocument();
  });

  it("shows a low-confidence warning for an uncertain record, not a confirmed-diagnosis message", async () => {
    fetchMock.mockReturnValueOnce(
      jsonResponse({
        analyses: [
          customMlEntry({
            customMl: {
              ...customMlEntry().customMl,
              accepted: false,
              uncertain: true,
              modelConfidence: 0.3,
            },
          }),
        ],
      })
    );
    render(<HistoryList />);

    await screen.findByText("Tomato Late Blight");
    expect(screen.getAllByText(/Low-confidence model result/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Confirmed disease/i)).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no analyses", async () => {
    fetchMock.mockReturnValueOnce(jsonResponse({ analyses: [] }));
    render(<HistoryList />);

    expect(await screen.findByText(/No analyses found/i)).toBeInTheDocument();
  });
});
