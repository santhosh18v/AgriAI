import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { AIChat } from "@/components/dashboard/AIChat";

export default function ChatPage() {
  return (
    <DashboardShell title="AI Advisor" subtitle="Chat with Gemini and Groq-powered farming experts">
      <AIChat />
    </DashboardShell>
  );
}
