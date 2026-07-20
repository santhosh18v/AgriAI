import { Camera, Cpu, ClipboardCheck } from "lucide-react";

const steps = [
  {
    number: "01",
    icon: Camera,
    title: "Capture or describe",
    description:
      "Take a photo of the affected crop, pest, or soil — or simply type out what you're observing in your field.",
  },
  {
    number: "02",
    icon: Cpu,
    title: "AI analyzes instantly",
    description:
      "Gemini Vision examines the image while Groq's Llama 3 cross-checks symptoms against known patterns — all in seconds.",
  },
  {
    number: "03",
    icon: ClipboardCheck,
    title: "Get your action plan",
    description:
      "Receive a clear diagnosis, confidence score, treatment steps, and prevention tips — with guidance on when to call an expert.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="py-24 px-6 relative">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-forest-950/10 to-transparent" />
      <div className="max-w-7xl mx-auto relative">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <span className="tag mb-4 inline-block">Workflow</span>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
            From field to fix in
            <span className="gradient-text-green"> three steps</span>
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-8 relative">
          {/* connecting line */}
          <div className="hidden md:block absolute top-12 left-[16%] right-[16%] h-px bg-gradient-to-r from-forest-700/0 via-forest-700/40 to-forest-700/0" />

          {steps.map((step) => {
            const Icon = step.icon;
            return (
              <div key={step.number} className="relative text-center">
                <div className="relative inline-flex items-center justify-center w-24 h-24 rounded-2xl glass-card mb-6 mx-auto">
                  <Icon className="w-9 h-9 text-forest-400" strokeWidth={1.5} />
                  <span className="absolute -top-3 -right-3 w-8 h-8 rounded-full bg-forest-600 flex items-center justify-center text-xs font-bold">
                    {step.number}
                  </span>
                </div>
                <h3 className="text-xl font-semibold mb-3">{step.title}</h3>
                <p className="text-white/50 text-sm leading-relaxed max-w-sm mx-auto">
                  {step.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
