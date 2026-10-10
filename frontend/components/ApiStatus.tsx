"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { api, type Health } from "@/lib/api";

export function ApiStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [state, setState] = useState<"checking" | "ok" | "down">("checking");

  useEffect(() => {
    let cancelled = false;
    const check = () =>
      api<Health>("/api/health")
        .then((h) => !cancelled && (setHealth(h), setState("ok")))
        .catch(() => !cancelled && setState("down"));
    check();
    const id = setInterval(check, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (state === "checking") return <Badge variant="outline">Checking API…</Badge>;
  if (state === "down")
    return <Badge className="bg-loss text-white">API offline - start the back end on port 8000</Badge>;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge className="bg-gain text-white">API connected</Badge>
      <Badge variant="outline">Model: {health?.llm_model ?? "not set"}</Badge>
      <Badge variant="outline">Voice engine: {health?.tts_engine}</Badge>
    </div>
  );
}
