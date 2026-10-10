"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Download, Music } from "lucide-react";
import { Button } from "@/components/ui/button";
import { API_URL } from "@/lib/api";
import { formatSeconds, type Job, type VideoFile } from "@/lib/scripts";
import { cn } from "@/lib/utils";

export type Lang = "en" | "ar";
/** What the player shows: a rendered language or an imported NotebookLM video. */
export type Source = Lang | "notebooklm";
const LABELS: Record<Source, string> = { en: "English", ar: "العربية", notebooklm: "NotebookLM" };
export type VideoPlayerHandle = { seek: (seconds: number) => void };
/** A jump request; a new nonce re-triggers the same time. Applied once the video can seek. */
export type SeekRequest = { seconds: number; nonce: number };

const url = (path: string, version: string) => `${API_URL}/outputs/${path}?v=${encodeURIComponent(version)}`;

/** HTML5 player with an English/Arabic switch, a captions track and downloads. */
export const VideoPlayer = forwardRef<
  VideoPlayerHandle,
  { job: Job; lang: Source; onLangChange: (lang: Source) => void; seekTo?: SeekRequest | null }
>(function VideoPlayer({ job, lang, onLangChange, seekTo }, ref) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pending = useRef<SeekRequest | null>(null);

  const applySeek = () => {
    const v = videoRef.current;
    const req = pending.current;
    if (!v || !req || v.readyState < 1) return;
    v.currentTime = req.seconds;
    pending.current = null;
    v.scrollIntoView({ behavior: "smooth", block: "center" });
    void v.play().catch(() => undefined);
  };

  useEffect(() => {
    if (!seekTo) return;
    pending.current = seekTo;
    applySeek(); // if the video is not loaded yet (e.g. after a language switch), onLoadedMetadata applies it
  }, [seekTo]);
  const [langs] = useState<Source[]>(() =>
    (["en", "ar", "notebooklm"] as Source[]).filter((l) => (l === "notebooklm" ? job.files.notebooklm : job.files[`video_${l}`])),
  );

  useImperativeHandle(ref, () => ({
    seek(seconds: number) {
      const v = videoRef.current;
      if (!v) return;
      v.currentTime = seconds;
      void v.play();
    },
  }));

  const nb = job.files.notebooklm;
  const file: Partial<VideoFile> & { video: string; duration: number } | undefined =
    lang === "notebooklm" ? nb : job.files[`video_${lang}`];
  if (!file) return <p className="text-sm text-muted-foreground">No {LABELS[lang]} video yet.</p>;
  const version = lang === "notebooklm" ? nb!.uploaded_at : file.rendered_at!;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border bg-card p-0.5">
          {langs.map((l) => (
            <button
              key={l}
              onClick={() => onLangChange(l)}
              className={cn(
                "rounded-md px-3 py-1 text-sm font-medium",
                l === lang ? "bg-brand-primary text-white" : "text-muted-foreground hover:text-brand-ink",
              )}
            >
              {LABELS[l]}
            </button>
          ))}
        </div>
        <span className="text-sm text-muted-foreground">{formatSeconds(file.duration)}</span>
      </div>

      <video
        key={`${lang}-${version}`}
        ref={videoRef}
        controls
        preload="metadata"
        poster={file.poster ? url(file.poster, version) : undefined}
        className="aspect-video w-full rounded-xl bg-black shadow-lg"
        crossOrigin="anonymous"
        onLoadedMetadata={applySeek}
      >
        <source src={url(file.video, version)} type="video/mp4" />
        {file.captions && (
          <track
            kind="captions"
            src={url(file.captions, version)}
            srcLang={lang}
            label={LABELS[lang]}
          />
        )}
      </video>

      <div className="flex flex-wrap items-center gap-2">
        <Button asChild size="sm" variant="outline">
          <a href={url(file.video, version)} download>
            <Download /> Full video (MP4)
          </a>
        </Button>
        {file.social && (
          <Button asChild size="sm" variant="outline">
            <a href={url(file.social, version)} download>
              <Download /> 15 s social cut
            </a>
          </Button>
        )}
        {file.captions && (
          <Button asChild size="sm" variant="ghost">
            <a href={url(file.captions, version)} download>
              <Download /> Captions (VTT)
            </a>
          </Button>
        )}
      </div>
      {lang === "notebooklm" && (
        <p className="text-xs text-muted-foreground">
          Imported from NotebookLM ({nb?.original_name}). Its figures were not checked by D-Storify; Q&amp;A jumps use the
          rendered videos.
        </p>
      )}
      {file.music_credit && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Music className="size-3.5" /> {file.music_credit.replace(/^Music: /, "")}
        </p>
      )}
    </div>
  );
});
