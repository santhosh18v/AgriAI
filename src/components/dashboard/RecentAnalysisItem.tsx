import Link from "next/link";
import { ScanLine, Bug, Droplets, CloudRain, Trash2, MessageSquare, ChevronRight } from "lucide-react";
import { cn } from "@/lib/auth";

const typeIcons: Record<string, any> = {
  crop_disease: ScanLine,
  pest: Bug,
  soil: Droplets,
  weather: CloudRain,
  waste: Trash2,
  general: MessageSquare,
};

export function RecentAnalysisItem({
  type,
  diagnosis,
  cropName,
  severity,
  confidence,
  createdAt,
}: {
  type: string;
  diagnosis: string;
  cropName?: string;
  severity: string;
  confidence: number;
  createdAt: string;
}) {
  const Icon = typeIcons[type] || MessageSquare;
  const date = new Date(createdAt);
  const timeAgo = getTimeAgo(date);

  return (
    <div className="flex items-center gap-4 p-4 rounded-xl hover:bg-white/[0.03] transition-colors group cursor-pointer">
      <div className="w-11 h-11 rounded-xl bg-white/5 flex items-center justify-center flex-shrink-0">
        <Icon className="w-5 h-5 text-white/50" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <p className="font-medium text-sm truncate">{diagnosis}</p>
          <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase flex-shrink-0", `severity-${severity}`)}>
            {severity}
          </span>
        </div>
        <p className="text-xs text-white/40">
          {cropName ? `${cropName} · ` : ""}
          {confidence}% confidence · {timeAgo}
        </p>
      </div>
      <ChevronRight className="w-4 h-4 text-white/20 group-hover:text-white/50 transition-colors flex-shrink-0" />
    </div>
  );
}

function getTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}
