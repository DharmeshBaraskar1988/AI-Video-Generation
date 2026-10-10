import { CheckCircle2, Circle, CircleStop, Loader2, PauseCircle, XCircle } from "lucide-react";
import { NODE_LABELS, type NodeStatus } from "@/lib/scripts";
import { cn } from "@/lib/utils";

const ICONS = {
  pending: Circle,
  running: Loader2,
  done: CheckCircle2,
  failed: XCircle,
  waiting: PauseCircle,
  stopped: CircleStop,
};

function seconds(n: NodeStatus): string | null {
  if (!n.started_at || !n.finished_at) return null;
  const s = (new Date(n.finished_at).getTime() - new Date(n.started_at).getTime()) / 1000;
  return s < 1 ? "<1s" : `${Math.round(s)}s`;
}

export function JobProgress({ nodes }: { nodes: NodeStatus[] }) {
  return (
    <ol className="space-y-2">
      {nodes.map((n) => {
        const Icon = ICONS[n.status] ?? Circle;
        return (
          <li key={n.name} className="flex items-start gap-2 text-sm">
            <Icon
              className={cn(
                "mt-0.5 size-4 shrink-0",
                n.status === "pending" && "text-muted-foreground",
                n.status === "running" && "animate-spin text-brand-primary",
                n.status === "done" && "text-gain",
                n.status === "failed" && "text-loss",
                n.status === "waiting" && "text-brand-accent",
                n.status === "stopped" && "text-muted-foreground",
              )}
            />
            <div className="min-w-0">
              <span className={cn(n.status === "pending" && "text-muted-foreground")}>
                {NODE_LABELS[n.name] ?? n.name}
              </span>
              {seconds(n) && <span className="ms-2 text-xs text-muted-foreground">{seconds(n)}</span>}
              {n.status === "waiting" && <span className="ms-2 text-xs text-brand-secondary">waiting for you</span>}
              {n.status === "stopped" && <span className="ms-2 text-xs text-muted-foreground">stopped</span>}
              {n.status === "running" && n.progress !== undefined && (
                <div className="mt-1 space-y-0.5">
                  <div className="h-1.5 w-40 rounded-full bg-muted">
                    <div className="h-1.5 rounded-full bg-brand-primary transition-all" style={{ width: `${n.progress}%` }} />
                  </div>
                  {n.detail && <p className="text-xs text-muted-foreground">{n.detail}</p>}
                </div>
              )}
              {n.error && <p className="text-xs break-words text-loss">{n.error}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
