import { MobileTopNav, PrimarySidebar } from "@/components/layout/primary-sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-dvh overflow-hidden">
      <PrimarySidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileTopNav />
        <main className="min-h-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
