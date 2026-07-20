"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { Save, Loader2, MapPin, Sprout, Globe } from "lucide-react";
import toast from "react-hot-toast";

const states = [
  "Andhra Pradesh", "Telangana", "Karnataka", "Tamil Nadu", "Maharashtra",
  "Punjab", "Haryana", "Uttar Pradesh", "Rajasthan", "Gujarat", "Other",
];

const cropOptions = [
  "Rice", "Wheat", "Cotton", "Sugarcane", "Maize", "Tomato", "Onion",
  "Chilli", "Groundnut", "Soybean", "Pulses", "Vegetables",
];

const languages = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी (Hindi)" },
  { value: "te", label: "తెలుగు (Telugu)" },
  { value: "ta", label: "தமிழ் (Tamil)" },
];

export function SettingsForm() {
  const { data: session, update } = useSession();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "",
    state: "",
    district: "",
    farmSize: "",
    soilType: "",
    irrigationType: "",
    cropTypes: [] as string[],
    language: "en",
  });

  useEffect(() => {
    fetch("/api/profile")
      .then((res) => res.json())
      .then((data) => {
        if (data.user) {
          setForm({
            name: data.user.name || "",
            state: data.user.location?.state || "",
            district: data.user.location?.district || "",
            farmSize: data.user.farmDetails?.size?.toString() || "",
            soilType: data.user.farmDetails?.soilType || "",
            irrigationType: data.user.farmDetails?.irrigationType || "",
            cropTypes: data.user.farmDetails?.cropTypes || [],
            language: data.user.language || "en",
          });
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const toggleCrop = (crop: string) => {
    setForm((prev) => ({
      ...prev,
      cropTypes: prev.cropTypes.includes(crop)
        ? prev.cropTypes.filter((c) => c !== crop)
        : [...prev.cropTypes, crop],
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          location: { state: form.state, district: form.district },
          farmDetails: {
            size: form.farmSize ? parseFloat(form.farmSize) : undefined,
            soilType: form.soilType,
            irrigationType: form.irrigationType,
            cropTypes: form.cropTypes,
          },
          language: form.language,
        }),
      });

      if (!res.ok) {
        toast.error("Failed to save settings");
        return;
      }

      toast.success("Settings saved successfully");
    } catch {
      toast.error("Something went wrong");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-5">
        {[1, 2, 3].map((i) => (
          <div key={i} className="glass-card h-48 shimmer rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-3xl">
      {/* Profile */}
      <div className="glass-card p-6 sm:p-8">
        <h3 className="font-semibold mb-5">Profile</h3>
        <div className="grid sm:grid-cols-2 gap-5">
          <div>
            <label className="label">Full name</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="input-field"
            />
          </div>
          <div>
            <label className="label">Email</label>
            <input value={session?.user?.email || ""} disabled className="input-field opacity-50" />
          </div>
        </div>
      </div>

      {/* Location */}
      <div className="glass-card p-6 sm:p-8">
        <div className="flex items-center gap-2 mb-5">
          <MapPin className="w-4 h-4 text-forest-400" />
          <h3 className="font-semibold">Location</h3>
        </div>
        <div className="grid sm:grid-cols-2 gap-5">
          <div>
            <label className="label">State</label>
            <select
              value={form.state}
              onChange={(e) => setForm({ ...form, state: e.target.value })}
              className="input-field"
            >
              <option value="" className="bg-slate-900">Select state</option>
              {states.map((s) => (
                <option key={s} value={s} className="bg-slate-900">{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">District</label>
            <input
              value={form.district}
              onChange={(e) => setForm({ ...form, district: e.target.value })}
              placeholder="e.g. Guntur"
              className="input-field"
            />
          </div>
        </div>
      </div>

      {/* Farm details */}
      <div className="glass-card p-6 sm:p-8">
        <div className="flex items-center gap-2 mb-5">
          <Sprout className="w-4 h-4 text-forest-400" />
          <h3 className="font-semibold">Farm details</h3>
        </div>
        <div className="grid sm:grid-cols-3 gap-5 mb-5">
          <div>
            <label className="label">Farm size (acres)</label>
            <input
              type="number"
              value={form.farmSize}
              onChange={(e) => setForm({ ...form, farmSize: e.target.value })}
              placeholder="e.g. 5"
              className="input-field"
            />
          </div>
          <div>
            <label className="label">Soil type</label>
            <input
              value={form.soilType}
              onChange={(e) => setForm({ ...form, soilType: e.target.value })}
              placeholder="e.g. Loamy"
              className="input-field"
            />
          </div>
          <div>
            <label className="label">Irrigation type</label>
            <input
              value={form.irrigationType}
              onChange={(e) => setForm({ ...form, irrigationType: e.target.value })}
              placeholder="e.g. Drip, Canal"
              className="input-field"
            />
          </div>
        </div>
        <div>
          <label className="label">Crops you grow</label>
          <div className="flex flex-wrap gap-2">
            {cropOptions.map((crop) => (
              <button
                key={crop}
                onClick={() => toggleCrop(crop)}
                className={`text-sm px-3 py-1.5 rounded-lg border transition-all ${
                  form.cropTypes.includes(crop)
                    ? "bg-forest-900/40 border-forest-500/50 text-forest-400"
                    : "bg-white/5 border-white/10 text-white/50 hover:border-white/20"
                }`}
              >
                {crop}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Language */}
      <div className="glass-card p-6 sm:p-8">
        <div className="flex items-center gap-2 mb-5">
          <Globe className="w-4 h-4 text-forest-400" />
          <h3 className="font-semibold">Language</h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {languages.map((lang) => (
            <button
              key={lang.value}
              onClick={() => setForm({ ...form, language: lang.value })}
              className={`text-sm px-3 py-2.5 rounded-lg border transition-all ${
                form.language === lang.value
                  ? "bg-forest-900/40 border-forest-500/50 text-forest-400"
                  : "bg-white/5 border-white/10 text-white/50 hover:border-white/20"
              }`}
            >
              {lang.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-white/30 mt-3">
          Hindi, Telugu, and Tamil response support is in active development.
        </p>
      </div>

      <button
        onClick={handleSave}
        disabled={saving}
        className="btn-primary px-8 py-3 disabled:opacity-60"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        Save changes
      </button>
    </div>
  );
}
