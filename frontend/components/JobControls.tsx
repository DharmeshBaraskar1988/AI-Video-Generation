"use client";

import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { Loader2, Play, RotateCcw, Square, StepForward } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { NODE_LABELS, type Job } from "@/lib/scripts";

type Action = "stop" | "resume" | "rerun" | "restart";

const label = (node: string | null | undefined) => (node ? (NODE_LABELS[node] ?? node) : null);

/** Stop a running job; resume a failed/stopped one; re-run from any step that has run; or start over. */
export function JobControls({ job, onChanged }: { job: Job; onChanged: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const [busy, setBusy] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rerunNode, setRerunNode] = useState("");

  const running = job.status === "running";
  const ended = job.status === "failed" || job.status === "stopped";
  const endedAt = job.nodes.find((n) => n.status === "failed" || n.status === "stopped")?.name ?? job.current_node;
  // Steps that have run in this job (human review is redone by editing and approving the script).
  const rerunnable = job.nodes.filter(
    (n) => n.name !== "human_review" && n.name !== "audio_review" && ["done", "failed", "stopped"].includes(n.status),
  );

  async function run(kind: Action) {
    if (kind === "restart" && !window.confirm("Regenerate from the start? A new script is drafted and your edits to this one are replaced."))
      return;
    if (kind === "rerun") {
      if (!rerunNode) return;
      const beforeReview = job.nodes.findIndex((n) => n.name === rerunNode) < job.nodes.findIndex((n) => n.name === "human_review");
      const warning = beforeReview
        ? `Re-run from "${label(rerunNode)}"? The script is rewritten from that step and goes back to review; edits made since then are replaced.`
        : `Re-run from "${label(rerunNode)}"? That step and every step after it run again.`;
      if (!window.confirm(warning)) return;
    }
    setBusy(kind);
    setError(null);
    try {
      if (kind === "stop") await api(`/api/scripts/${job.id}/stop`, { method: "POST" });
      else if (kind === "resume") await api(`/api/scripts/${job.id}/retry`, { method: "POST" });
      else if (kind === "rerun")
        await api(`/api/scripts/${job.id}/rerun`, { method: "POST", body: JSON.stringify({ node: rerunNode }) });
      else
        await api("/api/scripts", {
          method: "POST",
          body: JSON.stringify({ company: job.company, period: job.period, force: true }),
        });
      setRerunNode("");
      // A fresh run pauses for script review, which happens on the script page.
      const scriptPage = `/scripts/${job.id}`;
      if (kind === "restart" && pathname !== scriptPage) router.push(scriptPage);
      else onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const spin = (kind: Action, Icon: typeof Play) => (busy === kind ? <Loader2 className="animate-spin" /> : <Icon />);

  if (running) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-md border p-3">
        <p className="text-sm text-muted-foreground">
          {job.stop_requested
            ? `Stopping${job.current_node ? ` ${label(job.current_node)}` : ""}… (an LLM call already sent finishes first)`
            : `Running${job.current_node ? `: ${label(job.current_node)}` : ""}`}
        </p>
        <Button size="sm" variant="outline" className="ms-auto" onClick={() => run("stop")} disabled={busy !== null || job.stop_requested}>
          {job.stop_requested ? <Loader2 className="animate-spin" /> : spin("stop", Square)}
          {job.stop_requested ? "Stopping" : "Stop"}
        </Button>
        {error && <p className="w-full text-xs text-loss">{error}</p>}
      </div>
    );
  }

  return (
    <div
      className={
        job.status === "failed"
          ? "space-y-2 rounded-md border border-loss/40 bg-loss/5 p-3"
          : "space-y-2 rounded-md border p-3"
      }
    >
      {job.status === "failed" && (
        <p className="whitespace-pre-wrap text-sm text-loss">
          Generation failed{endedAt ? ` at ${label(endedAt)}` : ""}: {job.error}
        </p>
      )}
      {job.status === "stopped" && (
        <p className="text-sm">Stopped{endedAt ? ` at ${label(endedAt)}` : ""}. Resume where it stopped, re-run from any step, or start over.</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {ended && (
          <Button size="sm" onClick={() => run("resume")} disabled={busy !== null}>
            {spin("resume", StepForward)}
            Resume from {label(endedAt) ?? "where it ended"}
          </Button>
        )}
        {rerunnable.length > 0 && (
          <div className="flex items-center gap-1">
            <select
              value={rerunNode}
              onChange={(e) => setRerunNode(e.target.value)}
              className="h-8 w-48 min-w-0 truncate rounded-md border bg-background px-2 text-xs"
              aria-label="Re-run from step"
            >
              <option value="">Re-run from step…</option>
              {rerunnable.map((n) => (
                <option key={n.name} value={n.name}>
                  {label(n.name)}
                </option>
              ))}
            </select>
            <Button size="sm" variant="outline" onClick={() => run("rerun")} disabled={busy !== null || !rerunNode}>
              {spin("rerun", Play)}
              Re-run
            </Button>
          </div>
        )}
        <Button size="sm" variant="outline" onClick={() => run("restart")} disabled={busy !== null}>
          {spin("restart", RotateCcw)}
          Regenerate from start
        </Button>
      </div>
      {error && <p className="text-xs text-loss">{error}</p>}
    </div>
  );
}
