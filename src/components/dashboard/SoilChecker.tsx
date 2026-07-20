"use client";

import { useState } from "react";
import { Sparkles, Loader2, Droplets, Beaker, Sprout } from "lucide-react";
import toast from "react-hot-toast";
import { AnalysisResultCard } from "./AnalysisResultCard";

const soilTypes = ["Sandy", "Clay", "Loamy", "Silty", "Peaty", "Chalky", "Not sure"];
const cropGoals = ["Vegetables", "Cereals (Rice/Wheat)", "Pulses", "Cash crops (Cotton/Sugarcane)", "Fruits/Orchard"];

export function SoilChecker() {
  const [soilType, setSoilType] = useState("");
  const [cropGoal, setCropGoal] = useState("");
  const [observations, setObservations] = useState("");
  const [ph, setPh] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const handleAnalyze = async () => {
    if (!soilType && !observations) {
      toast.error("Please share your soil type or observations");
      return;
    }

    setLoading(true);
    setResult(null);

    const query = `Soil Analysis Request:
Soil type: ${soilType || "Unknown"}
${ph ? `pH level: ${ph}` : ""}
Intended crop/goal: ${cropGoal || "General farming"}
Observations: ${observations || "None provided"}

Please assess soil health, identify likely nutrient deficiencies or issues, and recommend amendments.`;

    try {
      const formData = new FormData();
      formData.append("type", "soil");
      formData.append("query", query);
      formData.append("provider", "groq");

      const res = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        toast.error(data.error || "Analysis failed");
        return;
      }

      setResult(data.result);
      toast.success("Soil analysis complete!");
    } catch {
      toast.error("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="glass-card p-6 sm:p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-11 h-11 rounded-xl bg-forest-500/15 flex items-center justify-center">
            <Droplets className="w-5 h-5 text-forest-400" />
          </div>
          <div>
            <h3 className="font-semibold">Soil Health Advisor</h3>
            <p className="text-sm text-white/40">Get personalized soil recommendations</p>
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-5 mb-5">
          <div>
            <label className="label">Soil type</label>
            <div className="grid grid-cols-2 gap-2">
              {soilTypes.map((s) => (
                <button
                  key={s}
                  onClick={() => setSoilType(s)}
                  className={`text-sm px-3 py-2 rounded-lg border transition-all ${
                    soilType === s
                      ? "bg-forest-900/40 border-forest-500/50 text-forest-400"
                      : "bg-white/5 border-white/10 text-white/50 hover:border-white/20"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="label">What do you want to grow?</label>
            <div className="space-y-2">
              {cropGoals.map((c) => (
                <button
                  key={c}
                  onClick={() => setCropGoal(c)}
                  className={`w-full text-left text-sm px-3 py-2 rounded-lg border transition-all ${
                    cropGoal === c
                      ? "bg-forest-900/40 border-forest-500/50 text-forest-400"
                      : "bg-white/5 border-white/10 text-white/50 hover:border-white/20"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mb-5">
          <label className="label flex items-center gap-2">
            <Beaker className="w-3.5 h-3.5" />
            Soil pH (if known)
          </label>
          <input
            type="text"
            value={ph}
            onChange={(e) => setPh(e.target.value)}
            placeholder="e.g. 6.5"
            className="input-field max-w-[150px]"
          />
        </div>

        <div className="mb-6">
          <label className="label flex items-center gap-2">
            <Sprout className="w-3.5 h-3.5" />
            Observations &amp; symptoms
          </label>
          <textarea
            value={observations}
            onChange={(e) => setObservations(e.target.value)}
            placeholder="e.g. Plants are stunted, leaves turning yellow, soil is hard and cracks when dry..."
            rows={4}
            className="input-field resize-none"
          />
        </div>

        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="btn-primary w-full sm:w-auto justify-center px-8 py-3.5 disabled:opacity-60"
        >
          {loading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Analyzing soil...
            </>
          ) : (
            <>
              <Sparkles className="w-5 h-5" />
              Get Soil Recommendations
            </>
          )}
        </button>
      </div>

      {result && !loading && (
        <AnalysisResultCard result={result} aiProvider="groq" />
      )}
    </div>
  );
}
