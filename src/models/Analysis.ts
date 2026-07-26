import mongoose, { Schema, Document } from "mongoose";

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
