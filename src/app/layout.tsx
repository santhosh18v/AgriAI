import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { Toaster } from "react-hot-toast";

export const metadata: Metadata = {
  title: "AgriAI — Agricultural Intelligence Platform",
  description:
    "AI-powered crop disease detection, pest identification, soil analysis, and farming guidance. Built for Indian farmers.",
  keywords: "agriculture, AI, crop disease, pest detection, soil health, farming",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-white antialiased">
        <Providers>
          {children}
          <Toaster
            position="top-right"
            toastOptions={{
              style: {
                background: "#1e2a1e",
                color: "#fff",
                border: "1px solid #16a34a",
              },
              success: { iconTheme: { primary: "#22c55e", secondary: "#fff" } },
              error: { iconTheme: { primary: "#ef4444", secondary: "#fff" } },
            }}
          />
        </Providers>
      </body>
    </html>
  );
}
