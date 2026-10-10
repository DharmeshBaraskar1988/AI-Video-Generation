"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, PlayCircle } from "lucide-react";
import { DeleteScriptButton } from "@/components/DeleteScriptButton";
import { JobControls } from "@/components/JobControls";
import { JobLog } from "@/components/JobLog";
import { JobProgress } from "@/components/JobProgress";
import { NarrationPlayers } from "@/components/NarrationPlayers";
import { ScriptEditor } from "@/components/ScriptEditor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import type { ScriptResponse } from "@/lib/scripts";

const STATUS_LABEL: Record<string, string> = {
  running: "Running",
  review: "Waiting for review",
  audio_review: "Waiting for audio approval",
  approved: "Approved",
  narrated: "Narrated",
  rendering: "Rendering",
  done: "Done",
  failed: "Failed",
  stopped: "Stopped",
};

export default function ScriptPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<ScriptResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const load = useCallback(() => {
    clearTimeout(timer.current);
    api<ScriptResponse>(`/api/scripts/${id}`)
      .then((d) => {
        setData(d);
        setError(null);
        if (d.job.status === "running") timer.current = setTimeout(load, 2000);
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
  // Keep the editor mounted after approval (the job briefly runs again while the graph resumes).
  const generating =
    job.status === "running" &&
    script?.status !== "approved" &&
    job.current_node !== "human_review";

  return (
    <div className="space-y-6">
      <Link
        href="/scripts"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline"
      >
        <ArrowLeft className="size-4" /> Scripts
      </Link>

      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-brand-primary">
          {script?.company_name_en.replace(" (demo source)", "") ??
            job.company.toUpperCase()}{" "}
          · {job.period}
        </h1>
        <Badge variant="outline">
          {STATUS_LABEL[job.status] ?? job.status}
        </Badge>
        {script?.derived && <Badge variant="outline">Derived figures</Badge>}
        {script?.demo && (
          <Badge className="bg-brand-secondary text-white">Demo data</Badge>
        )}
        <div className="ms-auto flex items-center gap-2">
          <DeleteScriptButton
            videoId={job.id}
            label={`${script?.company_name_en.replace(" (demo source)", "") ?? job.company.toUpperCase()} ${job.period}`}
            disabled={job.status === "running"}
            onDeleted={() => router.push("/scripts")}
          />
          {(job.files.video_en || job.files.video_ar) && (
            <Button asChild size="sm">
              <Link href={`/videos/${job.id}`}>
                <PlayCircle /> Watch video
              </Link>
            </Button>
          )}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
        <div className="min-w-0 space-y-4">
          <JobControls job={job} onChanged={() => setTimeout(load, 500)} />
          {generating && (
            <p className="text-sm text-muted-foreground">
              Writing the script. This takes about a minute on the Gemini free
              tier.
            </p>
          )}
          {script && !generating && <NarrationPlayers job={job} onChanged={() => setTimeout(load, 500)} />}
          {script && !generating && (
            <ScriptEditor
              key={script.created_at}
              initial={script}
              onApproved={() => setTimeout(load, 500)}
            />
          )}
        </div>

        <aside className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Progress</CardTitle>
            </CardHeader>
            <CardContent>
              <JobProgress nodes={job.nodes} />
            </CardContent>
          </Card>

          <JobLog
            videoId={job.id}
            running={job.status === "running"}
            failed={job.status === "failed"}
          />

          {script && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">How editing works</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs text-muted-foreground">
                <p>
                  <span className="rounded-md border border-brand-primary/30 bg-brand-primary/10 px-1.5 text-brand-primary">
                    figure
                  </span>{" "}
                  comes from the data file. Figures are locked: delete a chip or
                  add one with <em>Insert figure</em>; never type numbers.
                </p>
                <p>
                  <span className="rounded-md border border-dashed border-brand-accent bg-brand-accent/15 px-1.5 text-brand-ink">
                    figure
                  </span>{" "}
                  is derived (calculated, not reported).
                </p>
                <p>
                  Every save re-checks the numbers. Approve unlocks narration
                  and rendering.
                </p>
                <p className="pt-1">Model: {script.model}</p>
              </CardContent>
            </Card>
          )}
        </aside>
      </div>
    </div>
  );
}
