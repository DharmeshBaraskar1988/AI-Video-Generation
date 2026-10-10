"use client";

import { useState } from "react";
import { EyeOff, Globe, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Job } from "@/lib/scripts";

/** Publish / unpublish a finished video, or delete its rendered files (the script and narration stay). */
export function VideoActions({
  job,
  label,
  compact,
  onChanged,
}: {
  job: Job;
  label: string;
  compact?: boolean;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<"publish" | "delete" | null>(null);
  const running = job.status === "running";
  const published = Boolean(job.published);

  // The buttons may sit inside a link card.
  const stop = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  async function togglePublish(e: React.MouseEvent) {
    stop(e);
    setBusy("publish");
    try {
      await api(`/api/videos/${job.id}/publish`, { method: "POST", body: JSON.stringify({ published: !published }) });
      onChanged();
    } catch (err) {
      window.alert(`${published ? "Unpublish" : "Publish"} failed: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  async function remove(e: React.MouseEvent) {
    stop(e);
    if (
      !window.confirm(
        `Delete the video for ${label}? The English and Arabic videos, social cuts and captions are deleted. ` +
          "The script and narration are kept, so you can render it again from the script page.",
      )
    )
      return;
    setBusy("delete");
    try {
      await api(`/api/videos/${job.id}`, { method: "DELETE" });
      onChanged();
    } catch (err) {
      window.alert(`Delete failed: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <span className="flex items-center gap-1">
      <Button
        size={compact ? "xs" : "sm"}
        variant={published ? "outline" : "default"}
        disabled={running || busy !== null}
        onClick={togglePublish}
        title={running ? "Wait for the render to finish" : undefined}
      >
        {busy === "publish" ? <Loader2 className="animate-spin" /> : published ? <EyeOff /> : <Globe />}
        {published ? "Unpublish" : "Publish"}
      </Button>
      <Button
        size={compact ? "icon-xs" : "sm"}
        variant="ghost"
        className="text-loss hover:text-loss"
        disabled={running || busy !== null}
        onClick={remove}
        aria-label="Delete video"
        title="Delete video"
      >
        {busy === "delete" ? <Loader2 className="animate-spin" /> : <Trash2 />}
        {!compact && "Delete video"}
      </Button>
    </span>
  );
}
