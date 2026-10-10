"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, ExternalLink, FileText, Loader2, PlayCircle, RefreshCw, Save, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { METRIC_LABEL, pdfUrl, type Review, type ReviewContent, type Source } from "@/lib/documents";
import { cn } from "@/lib/utils";

function SourceChip({ source, active, onClick }: { source: Source | null; active: boolean; onClick: () => void }) {
  if (!source) return <span className="text-xs text-loss">no source</span>;
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 text-[11px] leading-5 whitespace-nowrap",
        active ? "border-brand-primary bg-brand-primary text-white" : "border-brand-primary/30 text-brand-primary",
      )}
    >
      <FileText className="size-3" /> {source.file.replace(/\.(pdf|md)$/i, "").slice(0, 28)} p.{source.page}
    </button>
  );
}

const fmt = (v: number | null | undefined, unit: string) =>
  v === null || v === undefined ? "—" : `${unit === "QR" ? "QR " : ""}${v.toLocaleString("en-US", { maximumFractionDigits: 3 })}${unit === "QR" ? "" : " m"}`;

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [review, setReview] = useState<Review | null>(null);
  const [content, setContent] = useState<ReviewContent | null>(null);
  const [source, setSource] = useState<{ key: string; src: Source; quote?: string } | null>(null);
  const [autoContinue, setAutoContinue] = useState(true);
  const [busy, setBusy] = useState<"save" | "approve" | "extract" | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [result, setResult] = useState<{ video_id: string; current_quarter: string; quarter_file: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const load = useCallback(() => {
    clearTimeout(timer.current);
    api<Review>(`/api/reviews/${id}`).then((r) => {
      setReview(r);
      setContent(r.content);
      if (r.status === "extracting") timer.current = setTimeout(load, 3000);
    });
  }, [id]);

  useEffect(() => {
    load();
    return () => clearTimeout(timer.current);
  }, [load]);

  if (!review || !content) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (review.status === "extracting")
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> The agent is extracting the figures…
      </p>
    );

  const update = (patch: Partial<ReviewContent>) => setContent((c) => (c ? { ...c, ...patch } : c));
  const setFigure = (fid: string, patch: Partial<ReviewContent["figures"][number]>) =>
    update({ figures: content.figures.map((f) => (f.id === fid ? { ...f, ...patch } : f)) });
  const target = content.figures.filter((f) => f.period === content.period);
  const prior = content.figures.filter((f) => f.period !== content.period);
  const approved = review.status === "approved";

  const save = async () => {
    setBusy("save");
    try {
      const r = await api<Review>(`/api/reviews/${id}`, { method: "PUT", body: JSON.stringify({ content }) });
      setReview(r);
      setMessage({ ok: true, text: "Saved." });
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const approve = async () => {
    setBusy("approve");
    setMessage(null);
    try {
      const r = await api<{ video_id: string; current_quarter: string; quarter_file: string }>(`/api/reviews/${id}/approve`, {
        method: "POST",
        body: JSON.stringify({ content, auto_continue: autoContinue }),
      });
      setResult(r);
      setMessage({
        ok: true,
        text: autoContinue
          ? `Approved. ${r.quarter_file} updated; the agent is now writing the ${r.current_quarter} video script and the summary.`
          : `Approved. ${r.quarter_file} updated.`,
      });
      load();
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const figureRows = (rows: ReviewContent["figures"]) =>
    rows.map((f) => (
      <tr key={f.id} className={cn("border-t align-top", !f.include && "opacity-50")}>
        <td className="py-2 pe-2">
          <input type="checkbox" checked={f.include} disabled={approved} onChange={(e) => setFigure(f.id, { include: e.target.checked })} className="accent-[var(--brand-primary)]" />
        </td>
        <td className="py-2 pe-2">
          <div className="font-medium">{METRIC_LABEL[f.metric]}</div>
          <div className="text-xs text-muted-foreground">{f.period}</div>
        </td>
        <td className="py-2 pe-2 text-xs">
          <span className="tabular">{f.value_text}</span> <span className="text-muted-foreground">{f.unit}</span>
        </td>
        <td className="py-2 pe-2">
          <div className="flex items-center gap-1">
            <Input
              type="number"
              step="any"
              value={f.value ?? ""}
              disabled={approved}
              onChange={(e) => setFigure(f.id, { value: e.target.value === "" ? null : Number(e.target.value) })}
              className={cn("h-8 w-32 text-sm tabular", f.value !== null && f.value < 0 && "text-loss")}
            />
            <span className="text-xs text-muted-foreground">{f.value_unit === "QR" ? "QR" : "QR m"}</span>
          </div>
        </td>
        <td className="py-2 pe-2 text-xs text-muted-foreground tabular">{fmt(f.existing, f.value_unit)}</td>
        <td className="py-2 pe-2">
          {f.verified ? (
            <Badge variant="outline" className="border-gain text-gain">
              <ShieldCheck className="size-3" /> found in source
            </Badge>
          ) : (
            <Badge variant="outline" className="border-loss text-loss" title={f.issues.join("; ")}>
              <AlertTriangle className="size-3" /> {f.issues[0]}
            </Badge>
          )}
        </td>
        <td className="py-2">
          <SourceChip
            source={f.source}
            active={source?.key === f.id}
            onClick={() => f.source && setSource(source?.key === f.id ? null : { key: f.id, src: f.source, quote: f.quote })}
          />
        </td>
      </tr>
    ));

  return (
    <div className="space-y-6">
      <Link href="/documents" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline">
        <ArrowLeft className="size-4" /> Documents
      </Link>
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-brand-primary">
          Review data · {content.company.name_en} · {content.period}
        </h1>
        <Badge variant="outline" className={cn(approved && "border-gain text-gain")}>
          {approved ? "Approved" : review.status === "failed" ? "Failed" : "Waiting for your approval"}
        </Badge>
        <span className="text-sm text-muted-foreground">
          {content.checks.verified}/{content.checks.figures} figures found in their source · extracted by {content.model}
        </span>
      </header>

      {message && (
        <p className={cn("rounded-md border p-2 text-sm", message.ok ? "border-gain/40 bg-gain/5 text-gain" : "border-loss/40 bg-loss/5 text-loss")}>
          {message.text}{" "}
          {result && autoContinue && (
            <Link href={`/scripts/${result.video_id}`} className="underline">
              Open the script
            </Link>
          )}
        </p>
      )}
      {approved && !result && content.current_quarter && (
        <p className="rounded-md border border-gain/40 bg-gain/5 p-2 text-sm text-gain">
          Approved {content.approved_at && new Date(content.approved_at).toLocaleString()} into {content.quarter_file}.{" "}
          <Link href={`/scripts/${content.company.slug}-${content.current_quarter.toLowerCase().replace(" ", "-")}`} className="underline">
            Open the {content.current_quarter} script
          </Link>{" "}
          ·{" "}
          <Link href="/summary" className="underline">
            Summary
          </Link>
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Company</CardTitle>
              <CardDescription>From documents: {content.documents.map((d) => d.name).join(", ")}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2 sm:grid-cols-3">
              <Input value={content.company.name_en} disabled={approved} onChange={(e) => update({ company: { ...content.company, name_en: e.target.value } })} />
              <Input value={content.company.name_ar} disabled={approved} dir="rtl" onChange={(e) => update({ company: { ...content.company, name_ar: e.target.value } })} />
              <Input value={content.company.ticker} disabled={approved} onChange={(e) => update({ company: { ...content.company, ticker: e.target.value } })} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Figures</CardTitle>
              <CardDescription>
                &quot;As printed&quot; is copied from the document; the program checked it is in the cited passage and converted it.
                Correct any value, untick anything you don&apos;t want used. &quot;In data file now&quot; is the value currently on the dashboard.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-start text-xs text-muted-foreground">
                  <tr>
                    <th className="pb-1 text-start">Use</th>
                    <th className="pb-1 text-start">Figure</th>
                    <th className="pb-1 text-start">As printed</th>
                    <th className="pb-1 text-start">Value used</th>
                    <th className="pb-1 text-start">In data file now</th>
                    <th className="pb-1 text-start">Check</th>
                    <th className="pb-1 text-start">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {figureRows(target)}
                  {prior.length > 0 && (
                    <tr>
                      <td colSpan={7} className="pt-4 pb-1 text-xs font-medium text-muted-foreground">
                        Same period last year (comparatives)
                      </td>
                    </tr>
                  )}
                  {figureRows(prior)}
                </tbody>
              </table>
              {content.figures.length === 0 && <p className="text-sm text-muted-foreground">No figures were found.</p>}
            </CardContent>
          </Card>

          {content.segments.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Revenue by segment</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1">
                {content.segments.map((sg) => (
                  <div key={sg.id} className={cn("flex flex-wrap items-center gap-2 text-sm", !sg.include && "opacity-50")}>
                    <input
                      type="checkbox"
                      checked={sg.include}
                      disabled={approved}
                      onChange={(e) => update({ segments: content.segments.map((x) => (x.id === sg.id ? { ...x, include: e.target.checked } : x)) })}
                      className="accent-[var(--brand-primary)]"
                    />
                    <span className="w-40">{sg.name}</span>
                    <span className="tabular w-16">{sg.share_pct}%</span>
                    {!sg.verified && <span className="text-xs text-loss">{sg.issues[0]}</span>}
                    <SourceChip source={sg.source} active={source?.key === sg.id} onClick={() => sg.source && setSource({ key: sg.id, src: sg.source })} />
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Reasons behind the results</CardTitle>
              <CardDescription>Used as key drivers in the video script (English and Arabic). Edit or untick freely.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {content.drivers.map((d) => (
                <div key={d.id} className={cn("space-y-1 rounded-lg border p-2", !d.include && "opacity-50")}>
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={d.include}
                      disabled={approved}
                      onChange={(e) => update({ drivers: content.drivers.map((x) => (x.id === d.id ? { ...x, include: e.target.checked } : x)) })}
                      className="accent-[var(--brand-primary)]"
                    />
                    <SourceChip source={d.source} active={source?.key === d.id} onClick={() => d.source && setSource({ key: d.id, src: d.source })} />
                    {d.issues.length > 0 && <span className="text-xs text-loss">{d.issues[0]}</span>}
                  </div>
                  <Input value={d.en} disabled={approved} onChange={(e) => update({ drivers: content.drivers.map((x) => (x.id === d.id ? { ...x, en: e.target.value } : x)) })} />
                  <Input value={d.ar} dir="rtl" lang="ar" disabled={approved} onChange={(e) => update({ drivers: content.drivers.map((x) => (x.id === d.id ? { ...x, ar: e.target.value } : x)) })} />
                </div>
              ))}
            </CardContent>
          </Card>

          {!approved && (
            <Card>
              <CardContent className="flex flex-wrap items-center gap-3 py-4">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={autoContinue} onChange={(e) => setAutoContinue(e.target.checked)} className="accent-[var(--brand-primary)]" />
                  After approval, write the video script and the summary automatically
                </label>
                <div className="ms-auto flex gap-2">
                  <Button
                    variant="ghost"
                    disabled={busy !== null}
                    onClick={async () => {
                      setBusy("extract");
                      await api(`/api/reviews/${id}/extract`, { method: "POST" });
                      setBusy(null);
                      setTimeout(load, 1500);
                    }}
                  >
                    {busy === "extract" ? <Loader2 className="animate-spin" /> : <RefreshCw />} Extract again
                  </Button>
                  <Button variant="outline" onClick={save} disabled={busy !== null}>
                    {busy === "save" ? <Loader2 className="animate-spin" /> : <Save />} Save edits
                  </Button>
                  <Button onClick={approve} disabled={busy !== null}>
                    {busy === "approve" ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Approve data
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
          {approved && result && (
            <Button asChild>
              <Link href={`/scripts/${result.video_id}`}>
                <PlayCircle /> Go to the {result.current_quarter} script
              </Link>
            </Button>
          )}
        </div>

        <aside>
          {source ? (
            <Card className="sticky top-4">
              <CardHeader>
                <CardTitle className="text-base break-words">{source.src.file}</CardTitle>
                <CardDescription>
                  Page {source.src.page}
                  {source.src.section && ` · ${source.src.section}`}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {source.quote && (
                  <p className="rounded-md border border-brand-accent bg-brand-accent/10 p-2 text-xs">
                    <span className="font-medium">Quoted:</span> {source.quote}
                  </p>
                )}
                <pre className="max-h-[55vh] overflow-auto rounded-md border bg-background/60 p-3 font-sans text-xs leading-5 whitespace-pre-wrap">
                  {source.src.text}
                </pre>
                <Button asChild size="sm" variant="outline">
                  <a href={pdfUrl(source.src)} target="_blank" rel="noreferrer">
                    <ExternalLink /> Open document at page {source.src.page}
                  </a>
                </Button>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-6 text-sm text-muted-foreground">
                Click a source chip to see the exact passage a figure was copied from.
              </CardContent>
            </Card>
          )}
        </aside>
      </div>
    </div>
  );
}
