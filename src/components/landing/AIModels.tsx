import { Eye, Zap, Brain, Gauge } from "lucide-react";

export function AIModels() {
  return (
    <section id="ai-models" className="py-24 px-6">
      <div className="max-w-7xl mx-auto">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <span className="tag mb-4 inline-block">Under the hood</span>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
            Two AI engines,
            <span className="gradient-text-green"> one mission</span>
          </h2>
          <p className="text-white/50 text-lg">
            We pair Google&apos;s Gemini for deep visual reasoning with
            Groq&apos;s blazing-fast Llama 3 inference for instant advisory
            chat.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          {/* Gemini Card */}
          <div className="glass-card p-8 relative overflow-hidden group">
            <div className="absolute -top-20 -right-20 w-56 h-56 bg-blue-500/10 rounded-full blur-3xl group-hover:bg-blue-500/15 transition-colors" />
            <div className="relative">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center">
                  <Eye className="w-6 h-6 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-xl font-semibold">Google Gemini</h3>
                  <p className="text-sm text-white/40">Vision &amp; Reasoning</p>
                </div>
              </div>
              <p className="text-white/60 mb-6 leading-relaxed">
                Gemini 1.5 Flash analyzes uploaded crop and soil images
                directly — identifying disease patterns, leaf discoloration,
                pest damage, and growth stage with multimodal precision.
              </p>
              <ul className="space-y-3">
                {[
                  "Multimodal image + text analysis",
                  "Detailed diagnostic reasoning",
                  "Contextual treatment plans",
                ].map((item) => (
                  <li key={item} className="flex items-center gap-3 text-sm text-white/70">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 flex-shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Groq Card */}
          <div className="glass-card p-8 relative overflow-hidden group">
            <div className="absolute -top-20 -right-20 w-56 h-56 bg-orange-500/10 rounded-full blur-3xl group-hover:bg-orange-500/15 transition-colors" />
            <div className="relative">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500/20 to-red-500/20 flex items-center justify-center">
                  <Zap className="w-6 h-6 text-orange-400" />
                </div>
                <div>
                  <h3 className="text-xl font-semibold">Groq + Llama 3</h3>
                  <p className="text-sm text-white/40">Real-time Advisory</p>
                </div>
              </div>
              <p className="text-white/60 mb-6 leading-relaxed">
                Groq&apos;s LPU inference engine runs Llama 3 at incredible
                speed — powering the live chat advisor for instant answers to
                farming questions, no matter how specific.
              </p>
              <ul className="space-y-3">
                {[
                  "Sub-second response times",
                  "Structured severity &amp; confidence scoring",
                  "Always-on advisory chat",
                ].map((item) => (
                  <li key={item} className="flex items-center gap-3 text-sm text-white/70">
                    <span className="w-1.5 h-1.5 rounded-full bg-orange-400 flex-shrink-0" />
                    <span dangerouslySetInnerHTML={{ __html: item }} />
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {/* Stats bar */}
        <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { icon: Gauge, value: "<2s", label: "Avg. response time" },
            { icon: Brain, value: "95%", label: "Diagnosis accuracy" },
            { icon: Eye, value: "30+", label: "Crops supported" },
            { icon: Zap, value: "24/7", label: "AI availability" },
          ].map((stat) => {
            const Icon = stat.icon;
            return (
              <div key={stat.label} className="glass-card p-5 text-center">
                <Icon className="w-5 h-5 text-forest-400 mx-auto mb-2" />
                <p className="text-2xl font-bold mb-1">{stat.value}</p>
                <p className="text-xs text-white/40">{stat.label}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
