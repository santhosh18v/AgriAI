import { Sprout } from "lucide-react";
import { cn } from "@/lib/auth";

export function Logo({ className, iconOnly }: { className?: string; iconOnly?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-forest-500 to-forest-700 shadow-lg shadow-forest-900/40">
        <Sprout className="w-5 h-5 text-white" strokeWidth={2.5} />
      </div>
      {!iconOnly && (
        <span className="text-xl font-bold tracking-tight">
          Agri<span className="text-forest-400">AI</span>
        </span>
      )}
    </div>
  );
}
