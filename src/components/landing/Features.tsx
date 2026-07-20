import {
  Microscope,
  Bug,
  Droplets,
  CloudRain,
  Trash2,
  MessageSquareText,
  Languages,
  Smartphone,
} from "lucide-react";

const features = [
  {
    icon: Microscope,
    title: "Crop Disease Detection",
    description:
      "Upload a leaf or plant photo and get instant identification of fungal, bacterial, or viral diseases with treatment steps.",
    color: "forest",
  },
  {
    icon: Bug,
    title: "Pest Identification",
    description:
      "Recognize common pests from images and receive organic and chemical control recommendations tailored to your crop.",
    color: "earth",
  },
  {
    icon: Droplets,
    title: "Soil Health Advisor",
    description:
      "Describe or photograph soil conditions to get pH insights, nutrient deficiency signs, and amendment suggestions.",
    color: "forest",
  },
  {
    icon: CloudRain,
    title: "Weather-Aware Guidance",
    description:
      "Location-based irrigation and planting advice that adapts to upcoming rainfall, temperature, and humidity.",
    color: "earth",
  },
  {
    icon: Trash2,
    title: "Waste Segregation Assistant",
    description:
      "Snap a photo of farm or household waste to learn proper segregation, composting, and disposal practices.",
    color: "forest",
  },
  {
    icon: MessageSquareText,
    title: "AI Advisory Chat",
    description:
      "Ask follow-up questions in plain language. Powered by Groq for instant replies and Gemini for deep reasoning.",
    color: "earth",
  },
  {
    icon: Languages,
    title: "Telugu &amp; Hindi Support",
    description:
      "Switch the interface and AI responses to your preferred regional language for easier understanding.",
    color: "forest",
  },
  {
    icon: Smartphone,
    title: "Mobile-First Design",
    description:
      "Built to work smoothly on low-end smartphones and slower networks common in rural areas.",
    color: "earth",
  },
];

export function Features() {
  return (
    <section id="features" className="py-24 px-6 relative">
      <div className="max-w-7xl mx-auto">
        <div className="text-center max-w-2xl mx-auto mb-16">
          <span className="tag mb-4 inline-block">Capabilities</span>
          <h2 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
            Everything a farm needs,
            <br />
            <span className="gradient-text-green">in one app</span>
          </h2>
          <p className="text-white/50 text-lg">
            From the field to your phone — diagnose, decide, and act with
            confidence using AI built for agriculture and the environment.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {features.map((feature, i) => {
            const Icon = feature.icon;
            return (
              <div
                key={feature.title}
                className="glass-card-hover p-6 group"
                style={{ animationDelay: `${i * 0.05}s` }}
              >
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center mb-5 ${
                    feature.color === "forest"
                      ? "bg-forest-500/15 text-forest-400"
                      : "bg-earth-500/15 text-earth-400"
                  } group-hover:scale-110 transition-transform duration-300`}
                >
                  <Icon className="w-6 h-6" strokeWidth={1.75} />
                </div>
                <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
                <p
                  className="text-sm text-white/50 leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: feature.description }}
                />
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
