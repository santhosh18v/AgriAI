"use client";

import { useEffect, useState } from "react";
import {
  ScanLine,
  Bug,
  Droplets,
  CloudRain,
  Trash2,
  MessageSquare,
  Filter,
  ChevronDown,
  ChevronUp,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/auth";
import { PersistedCustomMl, PersistedSecondaryOpinion, ProviderMetadata } from "@/lib/disease-analysis/types";
import {
  CustomMlSafetyNotes,
  CustomMlStatusBadge,
  FallbackNote,
  SecondaryOpinionNote,
  TopPredictionsList,
  formatPercent,
  providerLabel,
} from "./custom-ml-shared";

interface HistoryEntry {
  id: string;
  type: string;
  query: string;
  diagnosis: string;
  severity: string;
  confidence: number;
  treatment: string;
  prevention: string;
  expertAdvice?: string;
  cropName?: string;
  aiProvider: string;
  /** Milestone M9: present only for disease-analysis records that went
   * through the custom-ml flow -- absent (never a placeholder) on legacy
   * or non-disease-analysis records. */
  customMl?: PersistedCustomMl;
  providerMetadata?: ProviderMetadata;
  secondaryOpinion?: PersistedSecondaryOpinion;
  resultVersion?: number;
  createdAt: string;
}

const typeIcons: Record<string, any> = {
  crop_disease: ScanLine,
  pest: Bug,
  soil: Droplets,
  weather: CloudRain,
  waste: Trash2,
  general: MessageSquare,
};

const typeFilters = [
  { value: "all", label: "All types" },
  { value: "crop_disease", label: "Crop Disease" },
  { value: "pest", label: "Pest" },
  { value: "soil", label: "Soil" },
  { value: "weather", label: "Weather" },
  { value: "waste", label: "Waste" },
  { value: "general", label: "General" },
];

const severityFilters = [
  { value: "all", label: "All severities" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
  { value: "healthy", label: "Healthy" },
];

export function HistoryList() {
  const [analyses, setAnalyses] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [type, setType] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (type !== "all") params.set("type", type);
    if (severity !== "all") params.set("severity", severity);

    fetch(`/api/history?${params.toString()}`)
      .then((res) => res.json())
      .then((data) => {
        if (!data.error) setAnalyses(data.analyses || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [type, severity]);

  return (
    <div className="space-y-5">
      {/* Filters */}
      <div className="glass-card p-4 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-white/40">
          <Filter className="w-4 h-4" />
          Filter
        </div>
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm outline-none focus:border-forest-500/50"
        >
          {typeFilters.map((f) => (
            <option key={f.value} value={f.value} className="bg-slate-900">
              {f.label}
            </option>
          ))}
        </select>
        <select
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm outline-none focus:border-forest-500/50"
        >
          {severityFilters.map((f) => (
            <option key={f.value} value={f.value} className="bg-slate-900">
              {f.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-sm text-white/30">
          {analyses.length} result{analyses.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* List */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass-card h-20 shimmer rounded-2xl" />
          ))}
        </div>
      ) : analyses.length === 0 ? (
        <div className="glass-card p-16 text-center">
          <ScanLine className="w-10 h-10 text-white/15 mx-auto mb-3" />
          <p className="text-white/40">No analyses found matching your filters.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {analyses.map((a) => {
            const Icon = typeIcons[a.type] || MessageSquare;
            const isExpanded = expandedId === a.id;
            return (
              <div key={a.id} className="glass-card overflow-hidden">
                <button
                  onClick={() => setExpandedId(isExpanded ? null : a.id)}
                  className="w-full flex items-center gap-4 p-4 sm:p-5 text-left hover:bg-white/[0.02] transition-colors"
                >
                  <div className="w-11 h-11 rounded-xl bg-white/5 flex items-center justify-center flex-shrink-0">
                    <Icon className="w-5 h-5 text-white/50" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <p className="font-medium text-sm">{a.diagnosis}</p>
                      <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase", `severity-${a.severity}`)}>
                        {a.severity}
                      </span>
                      {a.cropName && <span className="tag">{a.cropName}</span>}
                      {a.customMl && <CustomMlStatusBadge customMl={a.customMl} />}
                    </div>
                    <p className="text-xs text-white/40">
                      {a.confidence}% confidence · {new Date(a.createdAt).toLocaleString()} ·{" "}
                      <span className="inline-flex items-center gap-1">
                        <Sparkles className="w-3 h-3" />
                        {providerLabel(a.aiProvider)}
                      </span>
                    </p>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-white/30 flex-shrink-0" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-white/30 flex-shrink-0" />
                  )}
                </button>

                {isExpanded && (
                  <div className="px-4 sm:px-5 pb-5 pt-1 border-t border-white/5 animate-fade-in">
                    <p className="text-sm text-white/50 mb-4 italic">&quot;{a.query}&quot;</p>

                    {/* Milestone M9: custom-ml detail panel -- only for
                        records that actually went through the custom-ml
                        flow. Renders safely (simply omitted) for legacy
                        records with no customMl field. */}
                    {a.customMl && (
                      <div className="mb-4 space-y-3">
                        {a.customMl.uncertain && (
                          <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
                            This was a low-confidence model result, not a confirmed diagnosis.
                          </p>
                        )}
                        <div className="bg-white/[0.03] rounded-xl p-4 grid sm:grid-cols-2 gap-3 text-xs">
                          <div>
                            <p className="text-white/40 mb-0.5">Model confidence</p>
                            <p className="text-white/70 font-medium">
                              {formatPercent(a.customMl.modelConfidence)} (threshold{" "}
                              {formatPercent(a.customMl.confidenceThreshold)})
                            </p>
                          </div>
                          <div>
                            <p className="text-white/40 mb-0.5">Crop / condition</p>
                            <p className="text-white/70 font-medium">
                              {a.customMl.crop} &middot; {a.customMl.condition}
                            </p>
                          </div>
                          <div className="sm:col-span-2">
                            <p className="text-white/40 mb-1">Top predictions</p>
                            <TopPredictionsList topPredictions={a.customMl.topPredictions} />
                          </div>
                        </div>
                        <CustomMlSafetyNotes customMl={a.customMl} />
                        {a.secondaryOpinion && <SecondaryOpinionNote secondaryOpinion={a.secondaryOpinion} />}
                        {a.providerMetadata && <FallbackNote providerMetadata={a.providerMetadata} />}
                      </div>
                    )}
                    {!a.customMl && a.providerMetadata?.fallbackUsed && (
                      <div className="mb-4">
                        <FallbackNote providerMetadata={a.providerMetadata} />
                      </div>
                    )}

                    <div className="grid sm:grid-cols-2 gap-4">
                      <div className="bg-white/[0.03] rounded-xl p-4">
                        <h4 className="text-xs font-semibold text-forest-400 uppercase mb-2">
                          Treatment
                        </h4>
                        <p className="text-sm text-white/60 whitespace-pre-line">{a.treatment}</p>
                      </div>
                      <div className="bg-white/[0.03] rounded-xl p-4">
                        <h4 className="text-xs font-semibold text-earth-400 uppercase mb-2">
                          Prevention
                        </h4>
                        <p className="text-sm text-white/60 whitespace-pre-line">{a.prevention}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
