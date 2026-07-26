import mongoose, { Schema, Document } from "mongoose";

import {
  APPROVED_CLASS_NAMES,
  PersistedCustomMl,
  PersistedSecondaryOpinion,
  ProviderMetadata,
  ResultVersion,
} from "@/lib/disease-analysis/types";

export interface IAnalysis extends Document {
  _id: any;
  userId: string;
  type: "crop_disease" | "pest" | "soil" | "weather" | "waste" | "general";
  imageUrl?: string;
  query: string;
  aiProvider: "gemini" | "groq" | "combined" | "custom-ml";
  result: {
    diagnosis: string;
    severity: "critical" | "high" | "medium" | "low" | "healthy";
    confidence: number;
    treatment: string;
    prevention: string;
    expertAdvice?: string;
    rawResponse: string;
  };
  /** Milestone M9: only present when the custom-ml classifier actually
   * produced a valid, independently-revalidated result -- see
   * lib/disease-analysis/persistence.ts's buildPersistedCustomMl. Never
   * fabricated on an infrastructure failure. */
  customMl?: PersistedCustomMl;
  /** Milestone M9: honest, single-source-of-truth provenance bookkeeping
   * for the disease-analysis flow -- see persistence.ts's
   * buildProviderMetadata. Only present for requests that went through
   * runDiseaseAnalysis (the custom-ml flow), never for plain Gemini/Groq
   * requests outside that flow. */
  providerMetadata?: ProviderMetadata;
  /** Milestone M9: a bounded Gemini secondary opinion attached to an
   * uncertain custom-ml result -- never ground truth, never a replacement
   * for `result`. */
  secondaryOpinion?: PersistedSecondaryOpinion;
  /** Milestone M9: 2 for documents written with customMl/providerMetadata/
   * secondaryOpinion awareness. Absent (never backfilled) on pre-M9
   * documents -- callers must treat a missing resultVersion as 1. */
  resultVersion?: ResultVersion;
  cropName?: string;
  location?: string;
  weather?: {
    temperature: number;
    humidity: number;
    rainfall: number;
  };
  tags: string[];
  helpful?: boolean;
  createdAt: Date;
}

const APPROVED_CLASS_NAME_LIST = [...APPROVED_CLASS_NAMES];

const TopPredictionSchema = new Schema(
  {
    className: { type: String, enum: APPROVED_CLASS_NAME_LIST, required: true },
    classIndex: { type: Number, required: true },
    modelConfidence: { type: Number, min: 0, max: 1, required: true },
  },
  { _id: false }
);

// Milestone M9: an entirely optional embedded subdocument -- `default:
// undefined` prevents Mongoose from initializing an empty {} (which would
// otherwise trigger the `required: true` validators below on every
// document that never had a custom-ml result).
const CustomMlSchema = new Schema(
  {
    className: { type: String, enum: APPROVED_CLASS_NAME_LIST, required: true },
    classIndex: { type: Number, required: true },
    crop: { type: String, enum: ["Tomato", "Potato"], required: true },
    condition: { type: String, required: true },
    healthy: { type: Boolean, required: true },
    modelConfidence: { type: Number, min: 0, max: 1, required: true },
    accepted: { type: Boolean, required: true },
    uncertain: { type: Boolean, required: true },
    confidenceLabel: { type: String, enum: ["model confidence"], required: true },
    productionCalibrated: {
      type: Boolean,
      required: true,
      validate: { validator: (v: boolean) => v === false, message: "productionCalibrated must be false" },
    },
    supportedClass: {
      type: Boolean,
      required: true,
      validate: { validator: (v: boolean) => v === true, message: "supportedClass must be true" },
    },
    confidenceThreshold: { type: Number, enum: [0.5], required: true },
    confidenceMethod: { type: String, enum: ["maximum_softmax_probability"], required: true },
    topPredictions: { type: [TopPredictionSchema], required: true },
    model: {
      architecture: { type: String, required: true },
      classCount: { type: Number, required: true },
    },
    limitations: { type: [String], default: [] },
  },
  { _id: false }
);

const SecondaryOpinionSchema = new Schema(
  {
    provider: { type: String, enum: ["gemini"], required: true },
    diagnosis: { type: String, required: true },
    severity: {
      type: String,
      enum: ["critical", "high", "medium", "low", "healthy"],
      required: true,
    },
    confidence: { type: Number, min: 0, max: 100, required: true },
    treatment: { type: String, required: true },
    prevention: { type: String, required: true },
    expertAdvice: String,
  },
  { _id: false }
);

const ProviderMetadataSchema = new Schema(
  {
    primaryProvider: { type: String, enum: ["custom-ml", "gemini"], required: true },
    persistedProvider: {
      type: String,
      enum: ["gemini", "groq", "custom-ml", "combined"],
      required: true,
    },
    fallbackUsed: { type: Boolean, required: true },
    fallbackProvider: { type: String, enum: ["custom-ml", "gemini"] },
    fallbackReason: {
      type: String,
      enum: ["service_unavailable", "timeout", "malformed_upstream", "service_not_ready", "uncertain_prediction"],
    },
    secondaryOpinionUsed: { type: Boolean, required: true },
  },
  { _id: false }
);

const AnalysisSchema = new Schema<IAnalysis>(
  {
    userId: { type: String, required: true, index: true },
    type: {
      type: String,
      enum: ["crop_disease", "pest", "soil", "weather", "waste", "general"],
      required: true,
    },
    imageUrl: String,
    query: { type: String, required: true },
    aiProvider: {
      type: String,
      // "custom-ml" added in Milestone M8 (AgriAI's own EfficientNet-B0
      // disease classifier). "combined" is used only when both custom-ml
      // and Gemini genuinely contributed to one result (an uncertain
      // custom-ml prediction with a Gemini secondary opinion attached) --
      // never as a stand-in for a single-provider result.
      enum: ["gemini", "groq", "combined", "custom-ml"],
      default: "gemini",
    },
    result: {
      diagnosis: { type: String, required: true },
      severity: {
        type: String,
        enum: ["critical", "high", "medium", "low", "healthy"],
        default: "medium",
      },
      confidence: { type: Number, min: 0, max: 100, default: 75 },
      treatment: String,
      prevention: String,
      expertAdvice: String,
      rawResponse: String,
    },
    // Milestone M9 additive fields -- all optional, all `default: undefined`
    // so pre-M9 documents (and non-disease-analysis documents) never get an
    // empty embedded object created for them. See IAnalysis's field
    // comments above for what each one means.
    customMl: { type: CustomMlSchema, required: false, default: undefined },
    providerMetadata: { type: ProviderMetadataSchema, required: false, default: undefined },
    secondaryOpinion: { type: SecondaryOpinionSchema, required: false, default: undefined },
    resultVersion: { type: Number, enum: [1, 2], required: false },
    cropName: String,
    location: String,
    weather: {
      temperature: Number,
      humidity: Number,
      rainfall: Number,
    },
    tags: [String],
    helpful: Boolean,
  },
  { timestamps: true }
);

export default mongoose.models.Analysis ||
  mongoose.model<IAnalysis>("Analysis", AnalysisSchema);
