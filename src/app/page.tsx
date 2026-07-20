import { Navbar } from "@/components/landing/Navbar";
import { Hero } from "@/components/landing/Hero";
import { Features } from "@/components/landing/Features";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { AIModels } from "@/components/landing/AIModels";
import { Pricing } from "@/components/landing/Pricing";
import { CTA, Footer } from "@/components/landing/CTAFooter";

export default function Home() {
  return (
    <main className="min-h-screen">
      <Navbar />
      <Hero />
      <Features />
      <HowItWorks />
      <AIModels />
      <Pricing />
      <CTA />
      <Footer />
    </main>
  );
}
