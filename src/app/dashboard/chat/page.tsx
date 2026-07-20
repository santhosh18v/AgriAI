import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { AIChat } from "@/components/dashboard/AIChat";

export default function ChatPage() {
  return (
    <DashboardShell title="AI Advisor" subtitle="Chat with Qwen3 Local and Gemini farming experts">
      <AIChat />
    </DashboardShell>
  );
}
