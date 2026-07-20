import { DashboardShell } from "@/components/dashboard/DashboardShell";
import { SettingsForm } from "@/components/dashboard/SettingsForm";

export default function SettingsPage() {
  return (
    <DashboardShell title="Settings" subtitle="Manage your profile, farm details, and preferences">
      <SettingsForm />
    </DashboardShell>
  );
}
