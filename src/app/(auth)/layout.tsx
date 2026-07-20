import Link from "next/link";
import { Logo } from "@/components/ui/Logo";
import { Leaf, Sparkles, ShieldCheck } from "lucide-react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-mesh">
      {/* Left: form */}
      <div className="flex flex-col justify-center px-6 sm:px-12 lg:px-20 py-12">
        <Link href="/" className="mb-12">
          <Logo />
        </Link>
        <div className="max-w-sm w-full mx-auto lg:mx-0">{children}</div>
      </div>

      {/* Right: visual panel */}
      <div className="hidden lg:flex relative items-center justify-center p-12 bg-gradient-to-br from-forest-950 via-slate-950 to-slate-925 border-l border-white/5 overflow-hidden">
        <div className="absolute top-1/4 -left-20 w-72 h-72 bg-forest-500/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 -right-20 w-80 h-80 bg-earth-500/10 rounded-full blur-3xl" />

        <div className="relative max-w-md space-y-8">
          <h2 className="text-3xl font-bold tracking-tight leading-tight">
            AI that knows your
            <span className="gradient-text-green"> fields</span>, your
            crops, and your soil.
          </h2>

          <div className="space-y-4">
            {[
              {
                icon: Leaf,
                title: "30+ crops supported",
                desc: "From paddy to tomato to cotton.",
              },
              {
                icon: Sparkles,
                title: "Instant AI diagnosis",
                desc: "Gemini Vision + Groq Llama 3 working together.",
              },
              {
                icon: ShieldCheck,
                title: "Privacy first",
                desc: "Your farm data stays yours, always.",
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.title} className="glass-card p-4 flex items-start gap-4">
                  <div className="w-10 h-10 rounded-lg bg-forest-500/15 flex items-center justify-center flex-shrink-0">
                    <Icon className="w-5 h-5 text-forest-400" />
                  </div>
                  <div>
                    <p className="font-semibold text-sm mb-0.5">{item.title}</p>
                    <p className="text-sm text-white/40">{item.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
