"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ScanLine,
  AlertTriangle,
  CheckCircle2,
  Activity,
  ArrowRight,
  Sparkles,
} from "lucide-react";
import { useSession } from "next-auth/react";
import { StatCard } from "./StatCard";
import { MonthlyTrendChart, SeverityPieChart, TypeBarChart } from "./Charts";
import { RecentAnalysisItem } from "./RecentAnalysisItem";

interface DashboardData {
  stats: {
    totalAnalyses: number;
    criticalIssues: number;
    resolvedIssues: number;
    analysisCount: number;
  };
  charts: {
    byType: { name: string; value: number }[];
    monthly: { month: string; count: number }[];
    severity: { name: string; value: number }[];
  };
  recentAnalyses: any[];
}

export function DashboardOverview() {
  const { data: session } = useSession();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/dashboard")
      .then((res) => res.json())
      .then((data) => {
        if (!data.error) setData(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const firstName = session?.user?.name?.split(" ")[0] || "there";

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass-card p-6 h-32 shimmer rounded-2xl" />
          ))}
        </div>
        <div className="grid lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2 glass-card h-80 shimmer rounded-2xl" />
          <div className="glass-card h-80 shimmer rounded-2xl" />
        </div>
      </div>
    );
  }

  const stats = data?.stats || {
    totalAnalyses: 0,
    criticalIssues: 0,
    resolvedIssues: 0,
    analysisCount: 0,
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Welcome banner */}
      <div className="glass-card p-6 sm:p-8 relative overflow-hidden">
        <div className="absolute -top-16 -right-16 w-56 h-56 bg-forest-500/10 rounded-full blur-3xl" />
        <div className="relative flex flex-col sm:flex-row sm:items-center justify-between gap-6">
          <div>
            <h2 className="text-2xl font-bold tracking-tight mb-2">
              Welcome back, {firstName} 👋
            </h2>
            <p className="text-white/50 max-w-lg">
              {stats.totalAnalyses === 0
                ? "Get started by scanning your first crop image or asking the AI advisor a question."
                : `You've run ${stats.totalAnalyses} analyses so far. Here's how your fields are doing.`}
            </p>
          </div>
          <Link href="/dashboard/scan" className="btn-primary flex-shrink-0">
            <Sparkles className="w-4 h-4" />
            New scan <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatCard
          icon={ScanLine}
          label="Total analyses"
          value={stats.totalAnalyses}
          color="forest"
        />
        <StatCard
          icon={AlertTriangle}
          label="Critical / High issues"
          value={stats.criticalIssues}
          color="red"
        />
        <StatCard
          icon={CheckCircle2}
          label="Marked resolved"
          value={stats.resolvedIssues}
          color="forest"
        />
        <StatCard
          icon={Activity}
          label="Lifetime AI requests"
          value={stats.analysisCount}
          color="earth"
        />
      </div>

      {/* Charts */}
      <div className="grid lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 glass-card p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">Analysis activity</h3>
            <span className="text-xs text-white/40">Last 6 months</span>
          </div>
          <MonthlyTrendChart data={data?.charts.monthly || []} />
        </div>
        <div className="glass-card p-6">
          <h3 className="font-semibold mb-2">Severity breakdown</h3>
          <SeverityPieChart data={data?.charts.severity || []} />
          {data?.charts.severity && data.charts.severity.length > 0 && (
            <div className="grid grid-cols-2 gap-2 mt-2">
              {data.charts.severity.map((s) => (
                <div key={s.name} className="flex items-center gap-2 text-xs">
                  <span className={`w-2.5 h-2.5 rounded-full severity-${s.name}`} />
                  <span className="capitalize text-white/60">{s.name}</span>
                  <span className="ml-auto font-medium">{s.value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-5">
        <div className="glass-card p-6">
          <h3 className="font-semibold mb-2">By category</h3>
          <TypeBarChart data={data?.charts.byType || []} />
        </div>

        <div className="lg:col-span-2 glass-card p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold">Recent analyses</h3>
            <Link href="/dashboard/history" className="text-xs text-forest-400 hover:text-forest-300 flex items-center gap-1">
              View all <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {data?.recentAnalyses && data.recentAnalyses.length > 0 ? (
            <div className="divide-y divide-white/5">
              {data.recentAnalyses.slice(0, 5).map((analysis) => (
                <RecentAnalysisItem key={analysis.id} {...analysis} />
              ))}
            </div>
          ) : (
            <div className="h-[200px] flex flex-col items-center justify-center text-center px-8">
              <ScanLine className="w-10 h-10 text-white/15 mb-3" />
              <p className="text-sm text-white/30 mb-4">
                No analyses yet. Scan a crop image to get started.
              </p>
              <Link href="/dashboard/scan" className="btn-secondary text-sm">
                Run your first scan
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
