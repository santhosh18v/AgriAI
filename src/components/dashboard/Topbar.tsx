"use client";

import { Menu, Bell, Search } from "lucide-react";

export function Topbar({
  title,
  subtitle,
  onMenuClick,
}: {
  title: string;
  subtitle?: string;
  onMenuClick: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 bg-slate-950/70 backdrop-blur-xl border-b border-white/5 px-6 py-5">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button onClick={onMenuClick} className="lg:hidden text-white/60">
            <Menu className="w-6 h-6" />
          </button>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight">{title}</h1>
            {subtitle && <p className="text-sm text-white/40 mt-0.5">{subtitle}</p>}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-3 py-2 w-64">
            <Search className="w-4 h-4 text-white/30" />
            <input
              placeholder="Search analyses..."
              className="bg-transparent text-sm outline-none placeholder-white/30 w-full"
            />
          </div>
          <button className="relative w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center hover:bg-white/10 transition-colors">
            <Bell className="w-[18px] h-[18px] text-white/60" />
            <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-forest-500" />
          </button>
        </div>
      </div>
    </header>
  );
}
