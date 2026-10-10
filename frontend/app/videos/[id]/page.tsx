"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Pencil } from "lucide-react";
import { JobControls } from "@/components/JobControls";
import { JobLog } from "@/components/JobLog";
import { JobProgress } from "@/components/JobProgress";
import { QAPanel, type QATimestamp } from "@/components/QAPanel";
import { VideoActions } from "@/components/VideoActions";
import { VideoPlayer, type Lang, type SeekRequest, type Source, type VideoPlayerHandle } from "@/components/VideoPlayer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { Job } from "@/lib/scripts";

type VideoResponse = {
  job: Job;
  script: { quarter: string; company_name_en: string; demo: boolean; derived: boolean; status: string } | null;
};

export default function VideoPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<VideoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState<Source>("en");
  const [seek, setSeek] = useState<SeekRequest | null>(null);
  const player = useRef<VideoPlayerHandle>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const load = useCallback(() => {
    clearTimeout(timer.current);
    api<VideoResponse>(`/api/videos/${id}`)
      .then((d) => {
        setData(d);
        setError(null);
        if (d.job.status === "running") timer.current = setTimeout(load, 3000);
      })
      .catch((e: Error) => setError(e.message));
  }, [id]);

  useEffect(() => {
    load();
    return () => clearTimeout(timer.current);
  }, [load]);

  if (error) return <p className="text-sm text-loss">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Loading…</p>;

  const { job, script } = data;
  const hasRendered = Boolean(job.files.video_en || job.files.video_ar);
  const hasVideo = hasRendered || Boolean(job.files.notebooklm);
  const available = (s: Source) => (s === "notebooklm" ? Boolean(job.files.notebooklm) : Boolean(job.files[`video_${s}`]));
  const activeLang: Source = available(lang) ? lang : (["en", "ar", "notebooklm"] as Source[]).find(available) ?? "en";
  const watchLang: Lang = activeLang === "notebooklm" ? "en" : activeLang;
  const jump = (t: QATimestamp) => {
    if (job.files[`video_${t.lang}`]) setLang(t.lang);
    setSeek({ seconds: t.seconds, nonce: Date.now() });
  };

  return (
    <div className="space-y-6">
      <Link href="/videos" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="size-4" /> Videos
      </Link>

      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-brand-primary">
          {script?.company_name_en.replace(" (demo source)", "") ?? job.company.toUpperCase()} · {job.period}
        </h1>
        {job.status === "running" && <Badge variant="outline">Rendering…</Badge>}
        {job.status === "failed" && <Badge className="bg-loss text-white">Failed</Badge>}
        {job.status === "stopped" && <Badge variant="outline">Stopped</Badge>}
        {script?.derived && <Badge variant="outline">Derived figures</Badge>}
        {script?.demo && <Badge className="bg-brand-secondary text-white">Demo data</Badge>}
        {hasVideo && (
          <Badge className={job.published ? "bg-gain text-white" : undefined} variant={job.published ? "default" : "outline"}>
            {job.published ? "Published" : "Unpublished"}
          </Badge>
        )}
        <div className="ms-auto flex flex-wrap items-center gap-2">
          {hasVideo && (
            <VideoActions
              job={job}
              label={`${job.company.toUpperCase()} ${job.period}`}
              onChanged={load}
            />
          )}
          <Button asChild size="sm" variant="outline">
            <Link href={`/scripts/${job.id}`}>
              <Pencil /> Edit script
            </Link>
          </Button>
        </div>
      </header>

      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="min-w-0 space-y-4">
          <JobControls job={job} onChanged={() => setTimeout(load, 500)} />
          {hasVideo ? (
            <VideoPlayer ref={player} job={job} lang={activeLang} onLangChange={setLang} seekTo={seek} />
          ) : (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                {job.status === "running"
                  ? "Rendering the video. English and Arabic take a few minutes each."
                  : "No video yet. Approve the script to render it."}
              </CardContent>
            </Card>
          )}
          {hasVideo && job.status === "running" && (
            <p className="text-sm text-muted-foreground">A new version is rendering; this page updates when it is ready.</p>
          )}
        </div>

        <aside className="space-y-4">
          {hasRendered && <QAPanel videoId={job.id} watchLang={watchLang} onJump={jump} />}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Progress</CardTitle>
            </CardHeader>
            <CardContent>
              <JobProgress nodes={job.nodes} />
            </CardContent>
          </Card>
          <JobLog videoId={job.id} running={job.status === "running"} failed={job.status === "failed"} />
        </aside>
      </div>
    </div>
  );
}
