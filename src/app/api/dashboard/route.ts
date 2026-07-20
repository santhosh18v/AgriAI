import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";

export const dynamic = "force-dynamic";
import { authOptions } from "@/lib/auth-options";
import connectDB from "@/lib/mongodb";
import Analysis from "@/models/Analysis";
import User from "@/models/User";

export async function GET(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    await connectDB();
    const userId = (session.user as any).id;

    const [analyses, user, recentAnalyses] = await Promise.all([
      Analysis.find({ userId }).lean(),
      User.findById(userId).lean(),
      Analysis.find({ userId })
        .sort({ createdAt: -1 })
        .limit(10)
        .lean(),
    ]);

    // Calculate stats
    const totalAnalyses = analyses.length;
    const criticalIssues = analyses.filter(
      (a) => a.result?.severity === "critical" || a.result?.severity === "high"
    ).length;
    const resolvedIssues = analyses.filter((a) => a.helpful === true).length;

    // Group by type
    const byType = analyses.reduce((acc: Record<string, number>, a) => {
      acc[a.type] = (acc[a.type] || 0) + 1;
      return acc;
    }, {});

    // Group by month (last 6 months)
    const sixMonthsAgo = new Date();
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);

    const monthlyData: Record<string, number> = {};
    analyses
      .filter((a) => new Date(a.createdAt) > sixMonthsAgo)
      .forEach((a) => {
        const month = new Date(a.createdAt).toLocaleString("default", {
          month: "short",
        });
        monthlyData[month] = (monthlyData[month] || 0) + 1;
      });

    // Severity distribution
    const severityData = analyses.reduce(
      (acc: Record<string, number>, a) => {
        const severity = a.result?.severity || "unknown";
        acc[severity] = (acc[severity] || 0) + 1;
        return acc;
      },
      {}
    );

    return NextResponse.json({
      stats: {
        totalAnalyses,
        criticalIssues,
        resolvedIssues,
        analysisCount: (user as any)?.analysisCount || 0,
      },
      charts: {
        byType: Object.entries(byType).map(([name, value]) => ({
          name: name.replace("_", " "),
          value,
        })),
        monthly: Object.entries(monthlyData).map(([month, count]) => ({
          month,
          count,
        })),
        severity: Object.entries(severityData).map(([name, value]) => ({
          name,
          value,
        })),
      },
      recentAnalyses: recentAnalyses.map((a) => ({
        id: a._id,
        type: a.type,
        query: a.query,
        diagnosis: a.result?.diagnosis,
        severity: a.result?.severity,
        confidence: a.result?.confidence,
        cropName: a.cropName,
        createdAt: a.createdAt,
      })),
    });
  } catch (error) {
    console.error("Dashboard error:", error);
    return NextResponse.json(
      { error: "Failed to load dashboard data" },
      { status: 500 }
    );
  }
}
