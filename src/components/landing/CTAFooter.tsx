import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

export function CTA() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="glass-card p-12 md:p-16 text-center relative overflow-hidden glow-green">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-96 bg-forest-500/10 rounded-full blur-3xl" />
          <div className="relative">
            <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
              Ready to scan your first crop?
            </h2>
            <p className="text-white/50 text-lg mb-8 max-w-xl mx-auto">
              Join farmers across India using AI to catch problems early and
              protect their harvest.
            </p>
            <Link href="/register" className="btn-primary px-8 py-3.5 text-base inline-flex">
              Create your free account <ArrowRight className="w-5 h-5" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-white/5 py-12 px-6">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
        <Logo />
        <p className="text-sm text-white/30 text-center">
          Built for the AI Model Development Contest 2026 — Indian Servers ·
          AI Agriculture / Environment Intelligence App
        </p>
        <div className="flex items-center gap-6 text-sm text-white/40">
          <a href="#features" className="hover:text-white transition-colors">Features</a>
          <a href="#pricing" className="hover:text-white transition-colors">Pricing</a>
          <Link href="/login" className="hover:text-white transition-colors">Sign in</Link>
        </div>
      </div>
    </footer>
  );
}
