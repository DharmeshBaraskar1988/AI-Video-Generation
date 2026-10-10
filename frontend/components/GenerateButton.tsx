"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Clapperboard, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export function GenerateButton({ company, period }: { company: string; period: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ video_id: string }>("/api/scripts", {
        method: "POST",
        body: JSON.stringify({ company, period }),
      });
      router.push(`/scripts/${res.video_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="w-full space-y-1">
      <Button className="w-full" onClick={generate} disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <Clapperboard />}
        Generate video
      </Button>
      {error && <p className="text-xs text-loss">{error}</p>}
    </div>
  );
}
