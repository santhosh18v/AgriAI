"use client";

import Link from "next/link";
import { ArrowRight, Leaf, Camera, Sparkles, TrendingUp } from "lucide-react";

export function Hero() {
  return (
    <section className="relative pt-40 pb-24 px-6 overflow-hidden bg-mesh">
      {/* Floating decorative elements */}
      <div className="absolute top-32 right-[10%] w-64 h-64 bg-forest-500/10 rounded-full blur-3xl animate-pulse-slow" />
      <div className="absolute bottom-20 left-[5%] w-72 h-72 bg-earth-500/5 rounded-full blur-3xl animate-pulse-slow" />

      <div className="max-w-7xl mx-auto relative">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          {/* Left: copy */}
          <div className="animate-fade-up">
            <div className="inline-flex items-center gap-2 glass-card px-4 py-2 mb-6 text-sm">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-forest-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-forest-500"></span>
              </span>
              <span className="text-white/70">Powered by Gemini Vision &amp; Groq Llama 3</span>
            </div>

            <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight leading-[1.05] mb-6">
              Your fields,
              <br />
              <span className="gradient-text">read by AI.</span>
            </h1>

            <p className="text-lg text-white/60 max-w-xl mb-10 leading-relaxed">
              Snap a photo of a sick crop, a pest, or your soil — get an instant
              diagnosis, treatment plan, and prevention guide. Built for Indian
              farms, in the language you speak.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 mb-12">
              <Link href="/register" className="btn-primary px-8 py-3.5 text-base">
                Start free analysis <ArrowRight className="w-5 h-5" />
              </Link>
              <a href="#how-it-works" className="btn-secondary px-8 py-3.5 text-base">
                See how it works
              </a>
            </div>

            <div className="flex items-center gap-8 text-sm text-white/40">
              <div className="flex items-center gap-2">
                <Leaf className="w-4 h-4 text-forest-500" />
                <span>30+ crop types</span>
              </div>
              <div className="flex items-center gap-2">
                <Camera className="w-4 h-4 text-forest-500" />
                <span>Instant photo scan</span>
              </div>
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-forest-500" />
                <span>95% accuracy</span>
              </div>
            </div>
          </div>

          {/* Right: visual mockup */}
          <div className="relative animate-fade-in" style={{ animationDelay: "0.2s" }}>
            <div className="relative glass-card p-3 glow-green animate-float">
              <div className="rounded-xl overflow-hidden bg-gradient-to-br from-forest-950 to-slate-900 aspect-[4/5] relative">
                {/* Mock phone screen */}
                <div className="absolute inset-0 p-5 flex flex-col">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-forest-500/20 flex items-center justify-center">
                        <Sparkles className="w-4 h-4 text-forest-400" />
                      </div>
                      <span className="text-sm font-semibold">Crop Scanner</span>
                    </div>
                    <span className="tag">Live</span>
                  </div>

                  <div className="flex-1 rounded-xl bg-gradient-to-br from-forest-900/60 to-earth-900/30 border border-white/5 mb-4 flex items-center justify-center relative overflow-hidden">
                    <div className="absolute inset-0 opacity-20" style={{
                      backgroundImage: "repeating-linear-gradient(45deg, #22c55e 0, #22c55e 1px, transparent 0, transparent 12px)"
                    }} />
                    <Leaf className="w-20 h-20 text-forest-500/40" strokeWidth={1} />
                    <div className="absolute top-3 left-3 right-3 h-px bg-forest-400/50 animate-pulse" />
                  </div>

                  <div className="space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-white/40">Diagnosis</span>
                      <span className="severity-medium px-2 py-0.5 rounded-full text-xs font-medium">Medium Risk</span>
                    </div>
                    <div className="glass-card p-3">
                      <p className="text-sm font-medium mb-1">Early Blight Detected</p>
                      <p className="text-xs text-white/40">Confidence: 92% · Tomato leaves</p>
                    </div>
                    <div className="flex gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-forest-500/30 overflow-hidden">
                        <div className="h-full w-[92%] bg-forest-500 rounded-full" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Floating badge cards */}
            <div className="absolute -left-6 top-12 glass-card p-4 hidden lg:block animate-float" style={{ animationDelay: "1s" }}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-earth-500/20 flex items-center justify-center">
                  <Sparkles className="w-5 h-5 text-earth-400" />
                </div>
                <div>
                  <p className="text-xs text-white/40">AI Chat</p>
                  <p className="text-sm font-semibold">Ask anything</p>
                </div>
              </div>
            </div>

            <div className="absolute -right-4 bottom-20 glass-card p-4 hidden lg:block animate-float" style={{ animationDelay: "2s" }}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-forest-500/20 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-forest-400" />
                </div>
                <div>
                  <p className="text-xs text-white/40">Yield trend</p>
                  <p className="text-sm font-semibold text-forest-400">+18% recovery</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
