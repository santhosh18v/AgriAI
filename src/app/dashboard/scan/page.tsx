import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { CropScanner } from "@/components/dashboard/CropScanner";

export default function ScanPage() {
  return (
    <DashboardShell
      title="Crop Scanner"
      subtitle="Upload a photo or describe an issue for instant AI diagnosis"
    >
      <CropScanner />
    </DashboardShell>
  );
}
