"use client";

import { useEffect, useState } from "react";
import { QuarterCard } from "@/components/QuarterCard";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import type { QuartersResponse } from "@/lib/quarters";

export function QuarterList() {
  const [data, setData] = useState<QuartersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<QuartersResponse>("/api/quarters")
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-sm text-loss">Could not load quarters: {error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Loading quarters…</p>;

  return (
    <div className="space-y-8">
      {data.errors.map((e) => (
        <p key={e.file} className="rounded-md border border-loss/40 bg-loss/5 p-3 text-sm text-loss">
          {e.file} could not be loaded: {e.error}
        </p>
      ))}

      {data.companies.length === 0 && (
        <p className="text-sm text-muted-foreground">No quarter files found in data/quarters.</p>
      )}

      {data.companies.map((c) => (
        <section key={c.id} className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-semibold text-brand-primary">{c.company.name_en}</h2>
            <span lang="ar" dir="rtl" className="text-muted-foreground">
              {c.company.name_ar}
            </span>
            <Badge variant="outline">
              {c.company.exchange}: {c.company.ticker}
            </Badge>
            {c.demo && (
              <Badge className="bg-brand-secondary text-white" title={c.note}>
                Demo data
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">Figures in {c.company.unit}</p>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {c.quarters.map((q) => (
              <QuarterCard key={q.id} company={c.id} quarter={q} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
