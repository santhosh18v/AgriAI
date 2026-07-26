"use client";

/**
 * Shared custom-ml display helpers (Milestone M9).
 *
 * Used by both AnalysisResultCard.tsx (the immediate analyze result) and
 * HistoryList.tsx (past analyses), so the two never describe the same
 * provider/status/limitations differently. Nothing here fabricates data --
 * every value rendered comes directly from the persisted/response
 * `customMl`/`providerMetadata`/`secondaryOpinion` fields (see
 * lib/disease-analysis/types.ts).
 */

import { AlertTriangle, CheckCircle2, Info } from "lucide-react";
import {
  FallbackReason,
  PersistedCustomMl,
  PersistedProvider,
  PersistedSecondaryOpinion,
  ProviderMetadata,
} from "@/lib/disease-analysis/types";

// Milestone M8/M9: "custom-ml" and "combined" alongside the pre-existing
// gemini/groq values (see src/models/Analysis.ts). Unknown values fall back
// to the raw string rather than being mislabeled as something else.
const providerLabels: Record<PersistedProvider, string> = {
  gemini: "Gemini Vision",
  groq: "Groq Llama 3",
  "custom-ml": "AgriAI Custom Model",
  combined: "AgriAI Custom Model + Gemini",
};

export function providerLabel(provider: string | undefined | null): string {
  if (!provider) return "Unknown";
  return providerLabels[provider as PersistedProvider] || provider;
}

const fallbackReasonLabels: Record<FallbackReason, string> = {
  service_unavailable: "the custom model service was unavailable",
  timeout: "the custom model took too long to respond",
  malformed_upstream: "the custom model returned an unexpected response",
  service_not_ready: "the custom model was not ready",
  uncertain_prediction: "the custom model's result was low-confidence",
};

export function fallbackReasonLabel(reason: FallbackReason | undefined | null): string {
  if (!reason) return "an infrastructure issue";
  return fallbackReasonLabels[reason] || reason;
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Renders the model's own accepted/uncertain status -- never phrased as a
 * "confirmed diagnosis". An uncertain result always shows a visible
 * low-confidence warning; an accepted result is labelled only "Model
 * prediction", never "Confirmed disease". */
export function CustomMlStatusBadge({
  customMl,
}: {
  customMl: Pick<PersistedCustomMl, "accepted" | "uncertain">;
}) {
  if (customMl.uncertain) {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
        <AlertTriangle className="w-3 h-3" />
        Low-confidence model result
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-forest-500/15 text-forest-400 border border-forest-500/30">
      <CheckCircle2 className="w-3 h-3" />
      Model prediction
    </span>
  );
}

export function TopPredictionsList({
  topPredictions,
}: {
  topPredictions: PersistedCustomMl["topPredictions"];
}) {
  if (!topPredictions?.length) return null;
  return (
    <ul className="space-y-1">
      {topPredictions.map((p) => (
        <li key={p.className} className="flex items-center justify-between text-xs text-white/60">
          <span>{p.className}</span>
          <span className="font-mono text-white/40">{formatPercent(p.modelConfidence)}</span>
        </li>
      ))}
    </ul>
  );
}

/** The fixed safety disclaimer block for any custom-ml result -- six-class
 * scope, no real-world field validation yet, and confidence !== calibrated
 * probability. Wording is intentionally identical regardless of
 * accepted/uncertain -- the model's own scope/validation limits don't
 * change based on how confident a single prediction was. */
export function CustomMlSafetyNotes({
  customMl,
}: {
  customMl: Pick<PersistedCustomMl, "limitations">;
}) {
  return (
    <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-4 text-xs text-white/50 leading-relaxed space-y-1.5">
      <p className="flex items-center gap-1.5 text-amber-400 font-semibold text-[11px] uppercase tracking-wide">
        <Info className="w-3.5 h-3.5" />
        Model limitations
      </p>
      <p>
        This model only recognizes six Tomato/Potato classes -- it has no opinion on any other
        crop or condition, and this confidence score is not production-calibrated.
      </p>
      <p>It has not yet been validated against real-world field conditions beyond its test dataset.</p>
      {customMl.limitations.map((l, i) => (
        <p key={i}>{l}</p>
      ))}
    </div>
  );
}

/** Never treated as ground truth or as confirmation of the primary
 * custom-ml result -- the wording says so explicitly. */
export function SecondaryOpinionNote({
  secondaryOpinion,
}: {
  secondaryOpinion: PersistedSecondaryOpinion;
}) {
  return (
    <div className="bg-sky-500/5 border border-sky-500/20 rounded-xl p-4">
      <p className="text-xs font-semibold text-sky-400 uppercase tracking-wide mb-2">
        Secondary opinion (Gemini) -- not a confirmation
      </p>
      <p className="text-sm text-white/60 mb-1">{secondaryOpinion.diagnosis}</p>
      <p className="text-xs text-white/40">
        This is a second, independent AI opinion sought because the custom model&apos;s result was
        low-confidence. It does not confirm or override the model&apos;s prediction.
      </p>
    </div>
  );
}

export function FallbackNote({ providerMetadata }: { providerMetadata: ProviderMetadata }) {
  if (!providerMetadata.fallbackUsed) return null;
  return (
    <p className="text-xs text-white/40">
      Fell back to {providerLabel(providerMetadata.fallbackProvider)} because{" "}
      {fallbackReasonLabel(providerMetadata.fallbackReason)}.
    </p>
  );
}
