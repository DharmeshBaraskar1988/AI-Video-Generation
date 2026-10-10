"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { DeleteScriptButton } from "@/components/DeleteScriptButton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { NODE_LABELS, type ScriptListItem } from "@/lib/scripts";

export default function ScriptsPage() {
  const [items, setItems] = useState<ScriptListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<ScriptListItem[]>("/api/scripts")
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(load, [load]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-brand-primary">Scripts</h1>
      {error && <p className="text-sm text-loss">{error}</p>}
      {items?.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No scripts yet. Press <strong>Generate video</strong> on a quarter in
          the{" "}
          <Link href="/" className="underline">
            dashboard
          </Link>
          .
        </p>
      )}
      <div className="grid gap-3">
        {items?.map((it) => (
          <Link key={it.id} href={`/scripts/${it.id}`}>
            <Card className="transition-colors hover:bg-sidebar-accent">
              <CardContent className="flex flex-wrap items-center gap-3">
                <span className="font-medium">{it.company.toUpperCase()}</span>
                <span>{it.period}</span>
                <Badge variant="outline" className="capitalize">
                  {it.status === "review" ? "Waiting for review" : it.status === "audio_review" ? "Waiting for audio approval" : it.status}
                </Badge>
                {it.status === "running" && it.current_node && (
                  <span className="text-xs text-muted-foreground">
                    {NODE_LABELS[it.current_node]}
                  </span>
                )}
                <span className="ms-auto flex items-center gap-2">
                  {it.checks && (
                    <span
                      className={`text-sm ${it.checks.passed ? "text-gain" : "text-loss"}`}
                    >
                      {it.checks.numbers_ok}/{it.checks.numbers_total} numbers
                      verified
                    </span>
                  )}
                  <DeleteScriptButton
                    compact
                    videoId={it.id}
                    label={`${it.company.toUpperCase()} ${it.period}`}
                    disabled={it.status === "running"}
                    onDeleted={load}
                  />
                </span>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
