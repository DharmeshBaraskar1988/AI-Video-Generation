import { ApiStatus } from "@/components/ApiStatus";
import { QuarterList } from "@/components/QuarterList";
import { VideoGrid } from "@/components/VideoGrid";
import brand from "@/lib/brand.generated.json";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-brand-primary">Dashboard</h1>
          <p className="text-sm text-muted-foreground">{brand.tagline_en}</p>
        </div>
        <ApiStatus />
      </header>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-brand-primary">Published videos</h2>
        <VideoGrid limit={6} published emptyText="No published videos yet. Publish one from the Videos page." />
      </section>
      <QuarterList />
    </div>
  );
}
