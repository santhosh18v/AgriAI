import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { HistoryList } from "@/components/dashboard/HistoryList";

export default function HistoryPage() {
  return (
    <DashboardShell title="History" subtitle="All your past AI analyses in one place">
      <HistoryList />
    </DashboardShell>
  );
}
