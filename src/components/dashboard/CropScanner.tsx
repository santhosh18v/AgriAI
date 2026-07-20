"use client";

import { useState } from "react";
import { Sparkles, Loader2, Leaf, Bug, Droplets, Trash2, CloudRain, Camera, Upload } from "lucide-react";
import toast from "react-hot-toast";
import { ImageDropzone } from "./ImageDropzone";
import { CameraCapture } from "./CameraCapture";
import { AnalysisResultCard } from "./AnalysisResultCard";
import { cn } from "@/lib/auth";

const analysisTypes = [
  { value: "crop_disease", label: "Crop Disease", icon: Leaf },
  { value: "pest", label: "Pest ID", icon: Bug },
  { value: "soil", label: "Soil Health", icon: Droplets },
  { value: "waste", label: "Waste Sort", icon: Trash2 },
  { value: "weather", label: "Weather Risk", icon: CloudRain },
];

export function CropScanner() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [type, setType] = useState("crop_disease");
  const [cropName, setCropName] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [aiProvider, setAiProvider] = useState<string>("");
  const [scanMode, setScanMode] = useState<"upload" | "camera">("upload");

  const handleImageSelect = (selectedFile: File) => {
    setFile(selectedFile);
    setPreview(URL.createObjectURL(selectedFile));
  };

  const handleRemoveImage = () => {
    setFile(null);
    setPreview(null);
  };

  const handleAnalyze = async () => {
    if (!query && !file) {
      toast.error("Please add a photo or describe what you're seeing");
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("type", type);
      formData.append(
        "query",
        query || `Analyze this ${type.replace("_", " ")} image and identify any issues.`
      );
      if (cropName) formData.append("cropName", cropName);
      if (file) formData.append("image", file);
      formData.append("provider", file ? "gemini" : "groq");

      const res = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        toast.error(data.error || "Analysis failed");
        setLoading(false);
        return;
      }

      setResult(data.result);
      setAiProvider(data.aiProvider);
      toast.success("Analysis complete!");
    } catch (error) {
      toast.error("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="glass-card p-6 sm:p-8">
        {/* Type selector */}
        <div className="mb-6">
          <label className="label">What are you analyzing?</label>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {analysisTypes.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.value}
                  onClick={() => setType(t.value)}
                  className={cn(
                    "flex flex-col items-center gap-2 p-3 rounded-xl border transition-all",
                    type === t.value
                      ? "bg-forest-900/40 border-forest-500/50 text-forest-400"
                      : "bg-white/5 border-white/10 text-white/50 hover:border-white/20"
                  )}
                >
                  <Icon className="w-5 h-5" />
                  <span className="text-xs font-medium text-center">{t.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Image upload / Camera Capture */}
        <div className="mb-6">
          <label className="label">Photo (optional but recommended)</label>

          {!preview && (
            <div className="flex gap-2 mb-4 bg-white/5 p-1 rounded-xl w-fit">
              <button
                type="button"
                onClick={() => setScanMode("upload")}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                  scanMode === "upload"
                    ? "bg-forest-500 text-white shadow-md"
                    : "text-white/60 hover:text-white"
                )}
              >
                <Upload className="w-4 h-4" />
                Upload Photo
              </button>
              <button
                type="button"
                onClick={() => setScanMode("camera")}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all",
                  scanMode === "camera"
                    ? "bg-forest-500 text-white shadow-md"
                    : "text-white/60 hover:text-white"
                )}
              >
                <Camera className="w-4 h-4" />
                Take Photo
              </button>
            </div>
          )}

          {preview ? (
            <ImageDropzone
              onImageSelect={handleImageSelect}
              preview={preview}
              onRemove={handleRemoveImage}
            />
          ) : scanMode === "camera" ? (
            <CameraCapture
              onCapture={(capturedFile) => {
                handleImageSelect(capturedFile);
                setScanMode("upload");
              }}
              onCancel={() => setScanMode("upload")}
            />
          ) : (
            <ImageDropzone
              onImageSelect={handleImageSelect}
              preview={preview}
              onRemove={handleRemoveImage}
            />
          )}
        </div>

        {/* Crop name */}
        <div className="mb-6">
          <label className="label">Crop / plant name (optional)</label>
          <input
            type="text"
            value={cropName}
            onChange={(e) => setCropName(e.target.value)}
            placeholder="e.g. Tomato, Paddy, Cotton, Wheat..."
            className="input-field"
          />
        </div>

        {/* Description */}
        <div className="mb-6">
          <label className="label">Describe what you&apos;re seeing</label>
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Yellow spots on lower leaves spreading upward, leaves curling at edges..."
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
              Analyzing with AI...
            </>
          ) : (
            <>
              <Sparkles className="w-5 h-5" />
              Run AI Analysis
            </>
          )}
        </button>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="glass-card p-8 text-center">
          <div className="inline-flex items-center gap-3 text-white/50">
            <Loader2 className="w-5 h-5 animate-spin text-forest-400" />
            <span className="text-sm">
              {file
                ? "Gemini Vision is examining your image..."
                : "Groq is processing your description..."}
            </span>
          </div>
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <AnalysisResultCard result={result} aiProvider={aiProvider} />
      )}
    </div>
  );
}
