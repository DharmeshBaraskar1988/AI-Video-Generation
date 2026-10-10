"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PlayCircle } from "lucide-react";
import { VideoActions } from "@/components/VideoActions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { api, API_URL } from "@/lib/api";
import { formatSeconds, type Job } from "@/lib/scripts";

/** Finished videos (at least one language rendered), newest first. `published` filters; `actions`
 * shows publish / delete buttons on each card. */
export function VideoGrid({
  limit,
  emptyText,
  published,
  actions,
}: {
  limit?: number;
  emptyText?: string;
  published?: boolean;
  actions?: boolean;
}) {
  const [videos, setVideos] = useState<Job[] | null>(null);

  const load = useCallback(() => {
    api<Job[]>(`/api/videos${published === undefined ? "" : `?published=${published}`}`)
      .then(setVideos)
      .catch(() => setVideos([]));
  }, [published]);

  useEffect(load, [load]);

  if (!videos) return null;
  if (!videos.length) return emptyText ? <p className="text-sm text-muted-foreground">{emptyText}</p> : null;

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {videos.slice(0, limit).map((v) => {
        const file = v.files.video_en ?? v.files.video_ar;
        const poster = file?.poster ?? v.files.notebooklm?.poster;
        const version = file?.rendered_at ?? v.files.notebooklm?.uploaded_at ?? "";
        return (
          <Link key={v.id} href={`/videos/${v.id}`}>
            <Card className="overflow-hidden pt-0 transition-shadow hover:shadow-md">
              <div className="relative aspect-video bg-brand-primary">
                {poster && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={`${API_URL}/outputs/${poster}?v=${encodeURIComponent(version)}`}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                )}
                <PlayCircle className="absolute inset-0 m-auto size-14 text-white/90 drop-shadow" />
                <Badge
                  className={
                    "absolute start-2 top-2 " +
                    (v.published ? "bg-gain text-white" : "bg-black/60 text-white")
                  }
                >
                  {v.published ? "Published" : "Unpublished"}
                </Badge>
              </div>
              <CardContent className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{v.company.toUpperCase()}</span>
                  <span>{v.period}</span>
                  {file && <span className="text-xs text-muted-foreground">{formatSeconds(file.duration)}</span>}
                  <span className="ms-auto flex gap-1">
                    {v.files.video_en && <Badge variant="outline">EN</Badge>}
                    {v.files.video_ar && <Badge variant="outline">AR</Badge>}
                    {v.files.notebooklm && <Badge variant="outline">NotebookLM</Badge>}
                    {v.status === "running" && <Badge variant="outline">Updating</Badge>}
                  </span>
                </div>
                {actions && (
                  <VideoActions job={v} label={`${v.company.toUpperCase()} ${v.period}`} compact onChanged={load} />
                )}
              </CardContent>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}
