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
