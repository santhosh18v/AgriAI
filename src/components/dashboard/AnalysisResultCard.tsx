"use client";

import { useState } from "react";
import {
  AlertTriangle,
  ShieldCheck,
  Sprout,
  Stethoscope,
  Gauge,
  ThumbsUp,
  ThumbsDown,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/auth";

interface AnalysisResult {
  diagnosis: string;
  severity: string;
  confidence: number;
  treatment: string;
  prevention: string;
  expertAdvice?: string;
  rawResponse: string;
}

const severityConfig: Record<string, { label: string; icon: any }> = {
  critical: { label: "Critical", icon: AlertTriangle },
  high: { label: "High Risk", icon: AlertTriangle },
  medium: { label: "Medium Risk", icon: Gauge },
  low: { label: "Low Risk", icon: ShieldCheck },
  healthy: { label: "Healthy", icon: Sprout },
};

export function AnalysisResultCard({
  result,
  aiProvider,
  analysisId,
}: {
  result: AnalysisResult;
  aiProvider: string;
  analysisId?: string;
}) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const config = severityConfig[result.severity] || severityConfig.medium;
  const Icon = config.icon;

  return (
    <div className="glass-card p-6 sm:p-8 animate-fade-up">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6 pb-6 border-b border-white/5">
        <div className="flex items-start gap-4">
          <div className={cn("w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0", `severity-${result.severity}`)}>
            <Icon className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={cn("px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase", `severity-${result.severity}`)}>
                {config.label}
              </span>
              <span className="tag flex items-center gap-1">
                <Sparkles className="w-3 h-3" />
                {aiProvider === "gemini" ? "Gemini Vision" : "Groq Llama 3"}
              </span>
            </div>
            <h3 className="text-xl font-semibold leading-snug">{result.diagnosis}</h3>
          </div>
        </div>

        <div className="text-right flex-shrink-0">
          <p className="text-3xl font-bold text-forest-400">{result.confidence}%</p>
          <p className="text-xs text-white/40">confidence</p>
        </div>
      </div>

      {/* Treatment & Prevention */}
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        <div className="bg-white/[0.03] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <Stethoscope className="w-4 h-4 text-forest-400" />
            <h4 className="font-semibold text-sm">Treatment plan</h4>
          </div>
          <p className="text-sm text-white/60 leading-relaxed whitespace-pre-line">
            {result.treatment}
          </p>
        </div>

        <div className="bg-white/[0.03] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <ShieldCheck className="w-4 h-4 text-earth-400" />
            <h4 className="font-semibold text-sm">Prevention tips</h4>
          </div>
          <p className="text-sm text-white/60 leading-relaxed whitespace-pre-line">
            {result.prevention}
          </p>
        </div>
      </div>

      {/* Expert advice */}
      {result.expertAdvice && (
        <div className="bg-earth-500/5 border border-earth-500/20 rounded-xl p-5 mb-6">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-earth-400" />
            <h4 className="font-semibold text-sm">When to consult an expert</h4>
          </div>
          <p className="text-sm text-white/60 leading-relaxed whitespace-pre-line">
            {result.expertAdvice}
          </p>
        </div>
      )}

      {/* Full response (collapsible) */}
      <details className="group">
        <summary className="cursor-pointer text-sm text-white/40 hover:text-white/60 transition-colors list-none flex items-center gap-2">
          <span className="group-open:rotate-90 transition-transform">▶</span>
          View full AI response
        </summary>
        <div className="mt-3 bg-black/20 rounded-xl p-4 text-sm text-white/50 whitespace-pre-line leading-relaxed max-h-96 overflow-y-auto">
          {result.rawResponse}
        </div>
      </details>

      {/* Feedback */}
      <div className="flex items-center justify-between mt-6 pt-6 border-t border-white/5">
        <p className="text-sm text-white/40">Was this analysis helpful?</p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFeedback("up")}
            className={cn(
              "w-9 h-9 rounded-lg flex items-center justify-center transition-colors",
              feedback === "up"
                ? "bg-forest-500/20 text-forest-400"
                : "bg-white/5 text-white/40 hover:text-white/60"
            )}
          >
            <ThumbsUp className="w-4 h-4" />
          </button>
          <button
            onClick={() => setFeedback("down")}
            className={cn(
              "w-9 h-9 rounded-lg flex items-center justify-center transition-colors",
              feedback === "down"
                ? "bg-red-500/20 text-red-400"
                : "bg-white/5 text-white/40 hover:text-white/60"
            )}
          >
            <ThumbsDown className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
