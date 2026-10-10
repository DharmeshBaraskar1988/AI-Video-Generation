"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Copy, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";

/** The job's log file (outputs/logs/{id}.log). Opens by itself when the job fails; polls while running. */
export function JobLog({ videoId, running, failed }: { videoId: string; running: boolean; failed: boolean }) {
  const [open, setOpen] = useState(failed);
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLPreElement>(null);

  const load = useCallback(() => {
    api<{ lines: string[] }>(`/api/scripts/${videoId}/log?lines=600`)
      .then((d) => {
        setLines(d.lines);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [videoId]);

  useEffect(() => {
    if (failed) setOpen(true);
  }, [failed]);

  useEffect(() => {
    if (!open) return;
    load();
    if (!running) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [open, running, load]);

  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 space-y-0">
        <button
          type="button"
          className="flex items-center gap-1 text-left"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          <CardTitle className="text-base">Logs</CardTitle>
        </button>
        {open && (
          <div className="ms-auto flex gap-1">
            <Button size="icon-sm" variant="ghost" onClick={load} title="Refresh">
              <RefreshCw className="size-3.5" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="size-7"
              title="Copy"
              onClick={() => navigator.clipboard?.writeText(lines.join("\n"))}
            >
              <Copy className="size-3.5" />
            </Button>
          </div>
        )}
      </CardHeader>
      {open && (
        <CardContent>
          {error && <p className="text-xs text-loss">{error}</p>}
          <pre
            ref={box}
            dir="ltr"
            className="max-h-96 overflow-auto rounded-md bg-muted p-2 font-mono text-[11px] leading-snug"
          >
            {lines.length === 0 ? (
              <span className="text-muted-foreground">No log yet. Logs are written from the next run on.</span>
            ) : (
              lines.map((l, i) => (
                <div
                  key={i}
                  className={cn(
                    "whitespace-pre-wrap break-all",
                    /FAILED|ERROR|Traceback|exit code [1-9]/.test(l) && "text-loss",
                    /=====/.test(l) && "pt-2 font-semibold",
                    /\bok \w+ done\b/.test(l) && "text-gain",
                  )}
                >
                  {l}
                </div>
              ))
            )}
          </pre>
        </CardContent>
      )}
    </Card>
  );
}
