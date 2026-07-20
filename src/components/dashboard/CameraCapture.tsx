"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, FlipHorizontal, X, AlertCircle } from "lucide-react";
import toast from "react-hot-toast";

interface CameraCaptureProps {
  onCapture: (file: File) => void;
  onCancel: () => void;
}

export function CameraCapture({ onCapture, onCancel }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [facingMode, setFacingMode] = useState<"user" | "environment">("environment");
  const [hasMultipleCameras, setHasMultipleCameras] = useState<boolean>(false);

  // Initialize camera
  useEffect(() => {
    async function startCamera() {
      // Stop any active streams before initiating a new one
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }

      try {
        const constraints = {
          video: {
            facingMode: facingMode,
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
          audio: false,
        };

        const mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
        setStream(mediaStream);
        setHasPermission(true);
        setError(null);

        if (videoRef.current) {
          videoRef.current.srcObject = mediaStream;
        }

        // Check if multiple video inputs are available
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter((device) => device.kind === "videoinput");
        setHasMultipleCameras(videoDevices.length > 1);
      } catch (err: any) {
        console.error("Error accessing camera:", err);
        setHasPermission(false);
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
          setError("Camera permission denied. Please enable camera access in your browser settings.");
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
          setError("No camera device found on this system.");
        } else {
          setError("Unable to access your device camera. Please check connection and permissions.");
        }
      }
    }

    startCamera();

    return () => {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facingMode]);

  const toggleCamera = () => {
    setFacingMode((prev) => (prev === "environment" ? "user" : "environment"));
  };

  const capturePhoto = () => {
    if (!videoRef.current || !stream) {
      toast.error("Camera is not ready yet.");
      return;
    }

    const video = videoRef.current;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      toast.error("Failed to process captured image.");
      return;
    }

    // Mirror image if front facing camera
    if (facingMode === "user") {
      ctx.translate(canvas.width, 0);
      ctx.scale(-1, 1);
    }

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          toast.error("Failed to capture crop photo.");
          return;
        }

        const file = new File([blob], `crop-capture-${Date.now()}.jpg`, {
          type: "image/jpeg",
        });

        // Stop camera tracks
        if (stream) {
          stream.getTracks().forEach((track) => track.stop());
        }

        onCapture(file);
      },
      "image/jpeg",
      0.9
    );
  };

  if (hasPermission === false) {
    return (
      <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-8 text-center space-y-4">
        <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center mx-auto text-red-400">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h3 className="font-semibold text-white">Camera Access Error</h3>
        <p className="text-sm text-white/60 max-w-md mx-auto">{error}</p>
        <div className="flex justify-center gap-3 pt-2">
          <button onClick={onCancel} className="btn-secondary px-6">
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative rounded-2xl overflow-hidden border border-white/10 bg-black/40 backdrop-blur-md">
      {/* Live Video Feed */}
      <div className="relative h-80 sm:h-96 w-full flex items-center justify-center bg-black">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={`w-full h-full object-cover ${facingMode === "user" ? "scale-x-[-1]" : ""}`}
        />

        {!stream && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80">
            <div className="text-center space-y-2">
              <div className="w-10 h-10 border-4 border-forest-500 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-xs text-white/50">Initializing camera feed...</p>
            </div>
          </div>
        )}
      </div>

      {/* Control Buttons Overlay */}
      <div className="p-4 bg-black/60 flex items-center justify-between gap-4">
        {/* Cancel button */}
        <button
          onClick={onCancel}
          type="button"
          className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 transition-all flex items-center justify-center text-white"
          title="Cancel"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Capture button */}
        <button
          onClick={capturePhoto}
          disabled={!stream}
          type="button"
          className="w-16 h-16 rounded-full bg-forest-500 hover:bg-forest-600 active:scale-95 disabled:opacity-50 disabled:active:scale-100 transition-all flex items-center justify-center text-white shadow-lg shadow-forest-500/25 border-4 border-white/15"
          title="Take Photo"
        >
          <Camera className="w-7 h-7" />
        </button>

        {/* Switch camera button */}
        {hasMultipleCameras ? (
          <button
            onClick={toggleCamera}
            type="button"
            className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 transition-all flex items-center justify-center text-white"
            title="Switch Camera"
          >
            <FlipHorizontal className="w-5 h-5" />
          </button>
        ) : (
          <div className="w-10 h-10" /> // spacer
        )}
      </div>
    </div>
  );
}
