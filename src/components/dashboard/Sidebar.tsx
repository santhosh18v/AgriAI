"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import {
  LayoutDashboard,
  ScanLine,
  MessageSquareText,
  History,
  Droplets,
  Settings,
  LogOut,
  X,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { cn } from "@/lib/auth";

const navItems = [
  { name: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { name: "Crop Scanner", href: "/dashboard/scan", icon: ScanLine },
  { name: "AI Advisor", href: "/dashboard/chat", icon: MessageSquareText },
  { name: "Soil Health", href: "/dashboard/soil", icon: Droplets },
  { name: "History", href: "/dashboard/history", icon: History },
  { name: "Settings", href: "/dashboard/settings", icon: Settings },
];

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const pathname = usePathname();
  const { data: session } = useSession();

  return (
    <div className="flex flex-col h-full bg-slate-925/80 backdrop-blur-xl border-r border-white/5">
      <div className="flex items-center justify-between px-6 py-6">
        <Logo />
        {onClose && (
          <button onClick={onClose} className="lg:hidden text-white/50">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      <nav className="flex-1 px-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            item.href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.name}
              href={item.href}
              onClick={onClose}
              className={cn("sidebar-link", isActive && "active")}
            >
              <Icon className="w-[18px] h-[18px]" strokeWidth={2} />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-white/5">
        <div className="flex items-center gap-3 px-3 py-2.5 mb-2 rounded-xl bg-white/[0.03]">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-forest-500 to-forest-700 flex items-center justify-center text-sm font-semibold flex-shrink-0">
            {session?.user?.name?.[0]?.toUpperCase() || "U"}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium truncate">{session?.user?.name || "User"}</p>
            <p className="text-xs text-white/40 truncate capitalize">
              {(session?.user as any)?.subscription || "free"} plan
            </p>
          </div>
        </div>
        <button
          onClick={() => signOut({ callbackUrl: "/" })}
          className="sidebar-link w-full text-red-400/70 hover:text-red-400 hover:bg-red-500/5"
        >
          <LogOut className="w-[18px] h-[18px]" />
          Sign out
        </button>
      </div>
    </div>
  );
}
