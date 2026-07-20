import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { SoilChecker } from "@/components/dashboard/SoilChecker";

export default function SoilPage() {
  return (
    <DashboardShell title="Soil Health" subtitle="Get AI-powered soil analysis and amendment advice">
      <SoilChecker />
    </DashboardShell>
  );
}
