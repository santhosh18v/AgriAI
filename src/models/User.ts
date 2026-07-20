import mongoose, { Schema, Document } from "mongoose";

export interface IUser extends Document {
  _id: any;
  name: string;
  email: string;
  password: string;
  avatar?: string;
  role: "farmer" | "expert" | "researcher" | "admin";
  location?: {
    state: string;
    district: string;
    coordinates?: { lat: number; lng: number };
  };
  farmDetails?: {
    size: number; // acres
    cropTypes: string[];
    soilType: string;
    irrigationType: string;
  };
  language: "en" | "hi" | "te" | "ta";
  analysisCount: number;
  subscription: "free" | "pro" | "enterprise";
  createdAt: Date;
  updatedAt: Date;
}

const UserSchema = new Schema<IUser>(
  {
    name: { type: String, required: true, trim: true },
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
    },
    password: { type: String, required: true, minlength: 6 },
    avatar: { type: String },
    role: {
      type: String,
      enum: ["farmer", "expert", "researcher", "admin"],
      default: "farmer",
    },
    location: {
      state: String,
      district: String,
      coordinates: {
        lat: Number,
        lng: Number,
      },
    },
    farmDetails: {
      size: Number,
      cropTypes: [String],
      soilType: String,
      irrigationType: String,
    },
    language: {
      type: String,
      enum: ["en", "hi", "te", "ta"],
      default: "en",
    },
    analysisCount: { type: Number, default: 0 },
    subscription: {
      type: String,
      enum: ["free", "pro", "enterprise"],
      default: "free",
    },
  },
  { timestamps: true }
);

export default mongoose.models.User ||
  mongoose.model<IUser>("User", UserSchema);
