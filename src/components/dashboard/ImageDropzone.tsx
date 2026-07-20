"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, ImageIcon } from "lucide-react";

export function ImageDropzone({
  onImageSelect,
  preview,
  onRemove,
}: {
  onImageSelect: (file: File) => void;
  preview: string | null;
  onRemove: () => void;
}) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles[0]) onImageSelect(acceptedFiles[0]);
    },
    [onImageSelect]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "image/*": [".png", ".jpg", ".jpeg", ".webp"] },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
  });

  if (preview) {
    return (
      <div className="relative rounded-2xl overflow-hidden border border-white/10 group">
        <img src={preview} alt="Selected crop" className="w-full h-72 object-cover" />
        <button
          onClick={onRemove}
          className="absolute top-3 right-3 w-9 h-9 rounded-full bg-black/60 backdrop-blur-sm flex items-center justify-center text-white hover:bg-red-500/80 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent p-4">
          <p className="text-sm text-white/80">Click to replace · {(preview.length / 1024).toFixed(0)}KB approx.</p>
        </div>
      </div>
    );
  }

  return (
    <div
      {...getRootProps()}
      className={`relative rounded-2xl border-2 border-dashed p-12 text-center cursor-pointer transition-all duration-200 ${
        isDragActive
          ? "border-forest-500 bg-forest-500/5"
          : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]"
      }`}
    >
      <input {...getInputProps()} />
      <div className="w-16 h-16 rounded-2xl bg-forest-500/10 flex items-center justify-center mx-auto mb-4">
        {isDragActive ? (
          <Upload className="w-7 h-7 text-forest-400" />
        ) : (
          <ImageIcon className="w-7 h-7 text-forest-400" />
        )}
      </div>
      <p className="font-medium mb-1">
        {isDragActive ? "Drop your image here" : "Drag &amp; drop a crop photo, or click to browse"}
      </p>
      <p className="text-sm text-white/40">PNG, JPG or WEBP — up to 10MB</p>
    </div>
  );
}
