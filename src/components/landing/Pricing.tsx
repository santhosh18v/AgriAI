import Link from "next/link";
import { Check } from "lucide-react";

const plans = [
  {
    name: "Free",
    price: "₹0",
    period: "forever",
    description: "For individual farmers getting started",
    features: [
      "5 AI analyses per day",
      "Crop disease detection",
      "Basic chat advisory (Groq)",
      "English language only",
      "Community support",
    ],
    cta: "Start free",
    highlighted: false,
  },
  {
    name: "Pro",
    price: "₹299",
    period: "/month",
    description: "For serious farmers and small co-ops",
    features: [
      "Unlimited AI analyses",
      "Crop, pest, soil &amp; waste detection",
      "Advanced chat (Gemini + Groq)",
      "Hindi &amp; Telugu support",
      "Weather-aware recommendations",
      "Analysis history &amp; trends",
      "Priority support",
    ],
    cta: "Start Pro trial",
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For agri-businesses and FPOs",
    features: [
      "Everything in Pro",
      "Multi-user team dashboards",
      "Custom crop datasets",
      "API access",
      "Dedicated agronomist line",
      "SLA &amp; onboarding support",
    ],
    cta: "Contact sales",
    highlighted: false,
  },
];

export function Pricing() {
  return (
    <section id="pricing" className="py-24 px-6">
      <div className="max-w-7xl mx-auto">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <span className="tag mb-4 inline-block">Pricing</span>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
            Simple plans for
            <span className="gradient-text-green"> every farm size</span>
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-6 items-stretch">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`relative p-8 rounded-2xl flex flex-col ${
                plan.highlighted
                  ? "bg-gradient-to-b from-forest-900/40 to-forest-950/40 border-2 border-forest-500/50 glow-green"
                  : "glass-card"
              }`}
            >
              {plan.highlighted && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-forest-500 text-white text-xs font-bold px-4 py-1 rounded-full">
                  Most Popular
                </span>
              )}
              <h3 className="text-lg font-semibold mb-1">{plan.name}</h3>
              <p className="text-sm text-white/40 mb-6">{plan.description}</p>
              <div className="mb-6">
                <span className="text-4xl font-bold">{plan.price}</span>
                <span className="text-white/40 text-sm">{plan.period}</span>
              </div>
              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-3 text-sm text-white/70">
                    <Check className="w-4 h-4 text-forest-400 flex-shrink-0 mt-0.5" />
                    <span dangerouslySetInnerHTML={{ __html: feature }} />
                  </li>
                ))}
              </ul>
              <Link
                href="/register"
                className={
                  plan.highlighted
                    ? "btn-primary w-full justify-center"
                    : "btn-secondary w-full justify-center"
                }
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
