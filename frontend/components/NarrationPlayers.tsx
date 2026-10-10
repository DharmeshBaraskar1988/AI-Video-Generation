"use client";

import Link from "next/link";
import { useState } from "react";
import { AudioLines, CheckCircle2, Loader2, Music, RotateCcw, Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { API_URL, api } from "@/lib/api";
import { formatSeconds, type AudioInfo, type Job } from "@/lib/scripts";

const LANGS = [
  { key: "audio_en", label: "English", dir: "ltr" },
  { key: "audio_ar", label: "العربية", dir: "rtl" },
] as const;

function Player({ info, label, version }: { info: AudioInfo; label: string; version: string }) {
  // Play the music preview (voice + track, mixed as in the video) when there is one.
  // version busts the browser cache after a re-narration.
  const src = `${API_URL}/outputs/${info.preview ?? info.audio}?v=${encodeURIComponent(version)}`;
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">
          {info.voice} · {formatSeconds(info.duration)}
          {info.rate && info.rate !== "+0%" ? ` · speed ${info.rate}` : ""}
        </span>
        {!info.timings_ok && <span className="text-xs text-loss">word timings need checking</span>}
      </div>
      <audio controls preload="metadata" src={src} className="w-full" />
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <Music className="size-3" />
        {info.music
          ? `${info.music}${info.music_volume !== undefined ? ` at ${Math.round(info.music_volume * 100)}% volume` : ""}${info.preview ? "" : " (preview mix failed; voice only)"}`
          : "No background music"}
      </p>
    </div>
  );
}

export function NarrationPlayers({ job, onChanged }: { job: Job; onChanged?: () => void }) {
  const [busy, setBusy] = useState<"approve" | "rerecord" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const narrating = job.status === "running" && (job.current_node === "tts_en" || job.current_node === "tts_ar");
  const reviewing = job.status === "audio_review";
  const available = LANGS.filter((l) => job.files?.[l.key]);
  if (!available.length && !narrating) return null;

  async function act(kind: "approve" | "rerecord") {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "approve") await api(`/api/scripts/${job.id}/approve-audio`, { method: "POST" });
      else await api(`/api/scripts/${job.id}/rerun`, { method: "POST", body: JSON.stringify({ node: "tts_en" }) });
      onChanged?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className={reviewing ? "border-brand-accent" : undefined}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <AudioLines className="size-5 text-brand-primary" />
          {reviewing ? "Audio review: listen, then approve to start the video" : "Narration"}
        </CardTitle>
        {reviewing && (
          <CardDescription>
            Each player has the voice-over with the background music, mixed the way the video will be. The video is
            only rendered after you approve the audio.
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          {narrating && <p className="text-sm text-muted-foreground md:col-span-2">Recording the voice-over…</p>}
          {!narrating &&
            available.map((l) => (
              <Player key={l.key} info={job.files[l.key]!} label={l.label} version={job.updated_at} />
            ))}
        </div>

        {reviewing && (
          <>
            <div className="flex items-start gap-2 rounded-md border bg-muted/40 p-3 text-sm">
              <Settings className="mt-0.5 size-4 shrink-0 text-brand-primary" />
              <p>
                Want a different voice or music? In{" "}
                <Link href="/admin" className="font-medium text-brand-primary underline">
                  Admin settings
                </Link>{" "}
                you can choose the <strong>voice for each language</strong> (English and Arabic, male or female), the
                speaking speed, and the <strong>royalty-free background music</strong> and its volume. You can also
                upload your own licensed track. Then come back and click <em>Re-record</em>.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => act("approve")} disabled={busy !== null}>
                {busy === "approve" ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                Approve audio and create video
              </Button>
              <Button variant="outline" onClick={() => act("rerecord")} disabled={busy !== null}>
                {busy === "rerecord" ? <Loader2 className="animate-spin" /> : <RotateCcw />}
                Re-record with current settings
              </Button>
            </div>
          </>
        )}
        {error && <p className="text-sm text-loss">{error}</p>}
      </CardContent>
    </Card>
  );
}
