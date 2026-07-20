"use client";

import Image from "next/image";
import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { ImageIcon, Upload, X } from "lucide-react";

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
      if (acceptedFiles[0]) {
        onImageSelect(acceptedFiles[0]);
      }
    },
    [onImageSelect]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "image/*": [".png", ".jpg", ".jpeg", ".webp"],
    },
    maxFiles: 1,
    maxSize: 10 * 1024 * 1024,
  });

  if (preview) {
    return (
      <div className="group relative h-72 overflow-hidden rounded-2xl border border-white/10">
        <Image
          src={preview}
          alt="Selected crop"
          fill
          unoptimized
          sizes="(max-width: 768px) 100vw, 50vw"
          className="object-cover"
        />

        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove selected image"
          className="absolute right-3 top-3 flex h-9 w-9 items-center justify-center rounded-full bg-black/60 text-white backdrop-blur-sm transition-colors hover:bg-red-500/80"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent p-4">
          <p className="text-sm text-white/80">
            Click to replace · {(preview.length / 1024).toFixed(0)}KB approx.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      {...getRootProps()}
      className={`relative cursor-pointer rounded-2xl border-2 border-dashed p-12 text-center transition-all duration-200 ${
        isDragActive
          ? "border-forest-500 bg-forest-500/5"
          : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]"
      }`}
    >
      <input {...getInputProps()} />

      <div className="bg-forest-500/10 mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl">
        {isDragActive ? (
          <Upload className="text-forest-400 h-7 w-7" />
        ) : (
          <ImageIcon className="text-forest-400 h-7 w-7" />
        )}
      </div>

      <p className="mb-1 font-medium">
        {isDragActive
          ? "Drop your image here"
          : "Drag & drop a crop photo, or click to browse"}
      </p>

      <p className="text-sm text-white/40">
        PNG, JPG or WEBP — up to 10MB
      </p>
    </div>
  );
}
