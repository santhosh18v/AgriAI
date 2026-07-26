import { beforeEach, describe, expect, it, vi } from "vitest";

const getServerSessionMock = vi.fn();
vi.mock("next-auth", () => ({ getServerSession: (...args: unknown[]) => getServerSessionMock(...args) }));
vi.mock("@/lib/auth-options", () => ({ authOptions: {} }));

const connectDBMock = vi.fn();
vi.mock("@/lib/mongodb", () => ({ default: (...args: unknown[]) => connectDBMock(...args) }));

const findMock = vi.fn();
const countDocumentsMock = vi.fn();
vi.mock("@/models/Analysis", () => ({
  default: {
    find: (...args: unknown[]) => findMock(...args),
    countDocuments: (...args: unknown[]) => countDocumentsMock(...args),
  },
}));

import { NextRequest } from "next/server";
import { GET } from "./route";

function makeChainable(result: unknown[]) {
  const chain: any = {
    sort: () => chain,
    skip: () => chain,
    limit: () => chain,
    lean: () => Promise.resolve(result),
  };
  return chain;
}

beforeEach(() => {
  vi.clearAllMocks();
  getServerSessionMock.mockResolvedValue({ user: { id: "user-123" } });
  connectDBMock.mockResolvedValue(undefined);
  countDocumentsMock.mockResolvedValue(1);
});

describe("GET /api/history -- Section 5/'history serialization does not crash'", () => {
  it("serializes a custom-ml-sourced analysis record without crashing", async () => {
    findMock.mockReturnValueOnce(
      makeChainable([
        {
          _id: "a1",
          type: "crop_disease",
          query: "spots on leaves",
          result: {
            diagnosis: "Tomato Late Blight",
            severity: "medium",
            confidence: 98,
            treatment: "Consult extension resources.",
            prevention: "Follow sanitation practices.",
          },
          cropName: "Tomato",
          aiProvider: "custom-ml",
          createdAt: new Date("2026-01-01T00:00:00Z"),
        },
      ])
    );

    const res = await GET(new NextRequest("http://localhost/api/history"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.analyses).toHaveLength(1);
    expect(body.analyses[0].aiProvider).toBe("custom-ml");
    expect(body.analyses[0].diagnosis).toBe("Tomato Late Blight");
  });

  it("serializes a 'combined'-sourced analysis record without crashing", async () => {
    findMock.mockReturnValueOnce(
      makeChainable([
        {
          _id: "a2",
          type: "crop_disease",
          query: "blurry leaf",
          result: { diagnosis: "Tomato Late Blight", severity: "medium", confidence: 30 },
          aiProvider: "combined",
          createdAt: new Date("2026-01-01T00:00:00Z"),
        },
      ])
    );

    const res = await GET(new NextRequest("http://localhost/api/history"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.analyses[0].aiProvider).toBe("combined");
  });

  it("returns 401 when unauthenticated (unchanged)", async () => {
    getServerSessionMock.mockResolvedValueOnce(null);
    const res = await GET(new NextRequest("http://localhost/api/history"));
    expect(res.status).toBe(401);
  });
});

describe("GET /api/history -- Milestone M9 field passthrough", () => {
  it("includes customMl/providerMetadata/resultVersion with the exact same field names as the analyze response", async () => {
    findMock.mockReturnValueOnce(
      makeChainable([
        {
          _id: "a3",
          type: "crop_disease",
          query: "spots on leaves",
          result: {
            diagnosis: "Tomato Late Blight",
            severity: "medium",
            confidence: 98,
            treatment: "Consult extension resources.",
            prevention: "Follow sanitation practices.",
          },
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
          createdAt: new Date("2026-01-01T00:00:00Z"),
        },
      ])
    );

    const res = await GET(new NextRequest("http://localhost/api/history"));
    const body = await res.json();

    expect(body.analyses[0].resultVersion).toBe(2);
    expect(body.analyses[0].customMl.modelConfidence).toBe(0.98);
    expect(body.analyses[0].customMl.model).toEqual({ architecture: "efficientnet_b0", classCount: 6 });
    expect(body.analyses[0].providerMetadata.persistedProvider).toBe("custom-ml");
    expect(body.analyses[0].secondaryOpinion).toBeUndefined();
  });

  it("includes a secondaryOpinion when present, flattened (no nested .result), matching the analyze response shape", async () => {
    findMock.mockReturnValueOnce(
      makeChainable([
        {
          _id: "a4",
          type: "crop_disease",
          query: "blurry leaf",
          result: { diagnosis: "Tomato Late Blight", severity: "medium", confidence: 30 },
          aiProvider: "combined",
          resultVersion: 2,
          secondaryOpinion: {
            provider: "gemini",
            diagnosis: "Possible late blight",
            severity: "medium",
            confidence: 60,
            treatment: "t2",
            prevention: "p2",
          },
          providerMetadata: {
            primaryProvider: "custom-ml",
            persistedProvider: "combined",
            fallbackUsed: true,
            fallbackProvider: "gemini",
            fallbackReason: "uncertain_prediction",
            secondaryOpinionUsed: true,
          },
          createdAt: new Date("2026-01-01T00:00:00Z"),
        },
      ])
    );

    const res = await GET(new NextRequest("http://localhost/api/history"));
    const body = await res.json();

    expect(body.analyses[0].secondaryOpinion.diagnosis).toBe("Possible late blight");
    expect(body.analyses[0].secondaryOpinion.result).toBeUndefined();
    expect(body.analyses[0].providerMetadata.fallbackReason).toBe("uncertain_prediction");
  });

  it("renders a pre-M9 legacy record safely -- no crash, and the M9 fields are simply absent", async () => {
    findMock.mockReturnValueOnce(
      makeChainable([
        {
          _id: "legacy-1",
          type: "crop_disease",
          query: "old record",
          result: {
            diagnosis: "Healthy",
            severity: "healthy",
            confidence: 80,
            treatment: "None needed.",
            prevention: "Keep monitoring.",
          },
          aiProvider: "gemini",
          createdAt: new Date("2025-01-01T00:00:00Z"),
          // No customMl, providerMetadata, secondaryOpinion, resultVersion
          // -- this is exactly what a document created before Milestone M9
          // looks like.
        },
      ])
    );

    const res = await GET(new NextRequest("http://localhost/api/history"));
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.analyses[0].diagnosis).toBe("Healthy");
    expect(body.analyses[0].customMl).toBeUndefined();
    expect(body.analyses[0].providerMetadata).toBeUndefined();
    expect(body.analyses[0].secondaryOpinion).toBeUndefined();
    expect(body.analyses[0].resultVersion).toBeUndefined();
  });
});
