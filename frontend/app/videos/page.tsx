"use client";

import { useState } from "react";
import { VideoGrid } from "@/components/VideoGrid";
import { Button } from "@/components/ui/button";

const FILTERS = [
  { key: "all", label: "All", value: undefined },
  { key: "published", label: "Published", value: true },
  { key: "unpublished", label: "Unpublished", value: false },
] as const;

export default function VideosPage() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const active = FILTERS.find((f) => f.key === filter)!;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-brand-primary">Videos</h1>
        <div className="ms-auto flex gap-1">
          {FILTERS.map((f) => (
            <Button key={f.key} size="sm" variant={f.key === filter ? "default" : "outline"} onClick={() => setFilter(f.key)}>
              {f.label}
            </Button>
          ))}
        </div>
      </header>
      <p className="text-sm text-muted-foreground">
        New videos start unpublished. Watch them, then publish. Only published videos show on the dashboard. Deleting a
        video removes the rendered files but keeps the script and narration.
      </p>
      <VideoGrid
        key={active.key}
        published={active.value}
        actions
        emptyText={
          active.value === true
            ? "No published videos yet."
            : active.value === false
              ? "No unpublished videos."
              : "No videos yet. Generate a script on the dashboard, approve it, and the video renders here."
        }
      />
    </div>
  );
}
