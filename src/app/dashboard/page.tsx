import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { DashboardOverview } from "@/components/dashboard/DashboardOverview";

export default function DashboardPage() {
  return (
    <DashboardShell title="Overview" subtitle="Your farm's AI-powered snapshot">
      <DashboardOverview />
    </DashboardShell>
  );
}
