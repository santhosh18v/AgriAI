import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";

export const dynamic = "force-dynamic";
import { authOptions } from "@/lib/auth-options";
import connectDB from "@/lib/mongodb";
import Analysis from "@/models/Analysis";

export async function GET(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const type = searchParams.get("type");
    const severity = searchParams.get("severity");
    const page = parseInt(searchParams.get("page") || "1");
    const limit = parseInt(searchParams.get("limit") || "20");

    await connectDB();

    const filter: any = { userId: (session.user as any).id };
    if (type && type !== "all") filter.type = type;
    if (severity && severity !== "all") filter["result.severity"] = severity;

    const [analyses, total] = await Promise.all([
      Analysis.find(filter)
        .sort({ createdAt: -1 })
        .skip((page - 1) * limit)
        .limit(limit)
        .lean(),
      Analysis.countDocuments(filter),
    ]);

    return NextResponse.json({
      analyses: analyses.map((a) => ({
        id: a._id,
        type: a.type,
        query: a.query,
        diagnosis: a.result?.diagnosis,
        severity: a.result?.severity,
        confidence: a.result?.confidence,
        treatment: a.result?.treatment,
        prevention: a.result?.prevention,
        cropName: a.cropName,
        aiProvider: a.aiProvider,
        createdAt: a.createdAt,
      })),
      pagination: {
        page,
        limit,
        total,
        pages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error("History error:", error);
    return NextResponse.json({ error: "Failed to load history" }, { status: 500 });
  }
}
