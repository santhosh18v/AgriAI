import { LucideIcon, TrendingUp, TrendingDown } from "lucide-react";

export function StatCard({
  icon: Icon,
  label,
  value,
  trend,
  trendUp,
  color = "forest",
}: {
  icon: LucideIcon;
  label: string;
  value: string | number;
  trend?: string;
  trendUp?: boolean;
  color?: "forest" | "earth" | "blue" | "red";
}) {
  const colorMap = {
    forest: "bg-forest-500/15 text-forest-400",
    earth: "bg-earth-500/15 text-earth-400",
    blue: "bg-blue-500/15 text-blue-400",
    red: "bg-red-500/15 text-red-400",
  };

  return (
    <div className="glass-card-hover p-6">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${colorMap[color]}`}>
          <Icon className="w-5 h-5" strokeWidth={1.75} />
        </div>
        {trend && (
          <div
            className={`flex items-center gap-1 text-xs font-medium ${
              trendUp ? "text-forest-400" : "text-red-400"
            }`}
          >
            {trendUp ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
            {trend}
          </div>
        )}
      </div>
      <p className="text-3xl font-bold tracking-tight mb-1">{value}</p>
      <p className="text-sm text-white/40">{label}</p>
    </div>
  );
}
