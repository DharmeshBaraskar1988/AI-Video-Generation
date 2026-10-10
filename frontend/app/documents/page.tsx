"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ClipboardCheck, FileText, FileUp, Loader2, Pencil, RefreshCw, Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { STATUS_LABEL, uploadFiles, type DocItem, type ReviewListItem } from "@/lib/documents";
import { cn } from "@/lib/utils";

const BUSY = new Set(["uploaded", "classifying", "classified", "indexed", "extracting"]);

function StatusBadge({ status }: { status: DocItem["status"] }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1",
        status === "failed" && "border-loss text-loss",
        status === "review" && "border-brand-accent text-brand-ink",
        status === "approved" && "border-gain text-gain",
      )}
    >
      {BUSY.has(status) && <Loader2 className="size-3 animate-spin" />}
      {status === "approved" && <CheckCircle2 className="size-3" />}
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

function EditDoc({ doc, onDone }: { doc: DocItem; onDone: () => void }) {
  const [company, setCompany] = useState(doc.company ?? "");
  const [period, setPeriod] = useState(doc.period ?? "");
  const [nameEn, setNameEn] = useState(doc.meta.company?.name_en ?? "");
  const [nameAr, setNameAr] = useState(doc.meta.company?.name_ar ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="mt-2 grid gap-2 rounded-md border bg-background/60 p-2 sm:grid-cols-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await api(`/api/documents/${doc.id}`, {
            method: "PATCH",
            body: JSON.stringify({ company, period, name_en: nameEn, name_ar: nameAr }),
          });
          onDone();
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Company code, e.g. iqcd" />
      <Input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="Period, e.g. H1 2026" />
      <Input value={nameEn} onChange={(e) => setNameEn(e.target.value)} placeholder="Company name (English)" />
      <Input value={nameAr} onChange={(e) => setNameAr(e.target.value)} placeholder="اسم الشركة" dir="rtl" />
      <Button type="submit" size="sm" disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Save and re-extract
      </Button>
      {error && <p className="text-xs text-loss sm:col-span-5">{error}</p>}
    </form>
  );
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocItem[] | null>(null);
  const [reviews, setReviews] = useState<ReviewListItem[]>([]);
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [report, setReport] = useState<{ name: string; status: string; reason?: string }[] | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const load = useCallback(() => {
    clearTimeout(timer.current);
    Promise.all([api<DocItem[]>("/api/documents"), api<ReviewListItem[]>("/api/reviews")]).then(([d, r]) => {
      setDocs(d);
      setReviews(r);
      if (d.some((x) => BUSY.has(x.status)) || r.some((x) => x.status === "extracting")) timer.current = setTimeout(load, 3000);
    });
  }, []);

  useEffect(() => {
    load();
    return () => clearTimeout(timer.current);
  }, [load]);

  const send = async (files: File[]) => {
    if (!files.length) return;
    setUploading(true);
    setReport(null);
    try {
      const r = await uploadFiles(files);
      setReport(r.report);
      setDocs(r.documents);
      load();
    } catch (e) {
      setReport([{ name: "upload", status: "error", reason: (e as Error).message }]);
    } finally {
      setUploading(false);
    }
  };

  const groups = new Map<string, DocItem[]>();
  for (const d of docs ?? []) {
    const key = d.company && d.period ? `${d.company}|${d.period}` : "|unidentified";
    groups.set(key, [...(groups.get(key) ?? []), d]);
  }
  const reviewFor = (company: string, period: string) => reviews.find((r) => r.company === company && r.period === period);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-brand-primary">Documents</h1>
        <p className="text-sm text-muted-foreground">
          Upload a company&apos;s results documents. The agent identifies the company and period, indexes them, extracts the
          figures with their sources, and asks you to approve. The summary and the video script follow automatically.
        </p>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          void send(Array.from(e.dataTransfer.files));
        }}
        onClick={() => input.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed bg-card p-8 text-center transition-colors",
          drag ? "border-brand-primary bg-brand-primary/5" : "border-border hover:border-brand-primary/50",
        )}
      >
        {uploading ? <Loader2 className="size-8 animate-spin text-brand-primary" /> : <FileUp className="size-8 text-brand-primary" />}
        <p className="font-medium">Drop PDF or Markdown files here, or click to choose</p>
        <p className="text-xs text-muted-foreground">Financial statements, press releases, investor presentations · up to 40 MB each</p>
        <input
          ref={input}
          type="file"
          multiple
          accept=".pdf,.md,.markdown"
          className="hidden"
          onChange={(e) => {
            void send(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
      </div>

      {report && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {report.map((r, i) => (
            <Badge key={i} variant="outline" className={r.status === "queued" ? "text-gain" : "text-loss"}>
              {r.name}: {r.status}
              {r.reason && ` (${r.reason})`}
            </Badge>
          ))}
          <button onClick={() => setReport(null)} aria-label="Dismiss">
            <X className="size-4 text-muted-foreground" />
          </button>
        </div>
      )}

      {docs?.length === 0 && <p className="text-sm text-muted-foreground">No documents yet.</p>}

      {[...groups.entries()].map(([key, items]) => {
        const [company, period] = key.split("|");
        const review = company ? reviewFor(company, period) : undefined;
        const name = items.find((d) => d.meta.company?.name_en)?.meta.company?.name_en ?? company.toUpperCase();
        return (
          <Card key={key}>
            <CardHeader className="flex flex-row flex-wrap items-center gap-2">
              <CardTitle className="text-base">
                {company ? (
                  <>
                    {name} · {period}
                  </>
                ) : (
                  "Not identified yet"
                )}
              </CardTitle>
              {review && (
                <Badge
                  variant="outline"
                  className={cn(review.status === "approved" && "border-gain text-gain", review.status === "failed" && "text-loss")}
                >
                  Data: {review.status}
                  {review.checks && ` · ${review.checks.verified}/${review.checks.figures} figures verified`}
                </Badge>
              )}
              {review && review.status !== "extracting" && (
                <Button asChild size="sm" className="ms-auto" variant={review.status === "review" ? "default" : "outline"}>
                  <Link href={`/documents/review/${review.id}`}>
                    <ClipboardCheck /> {review.status === "review" ? "Review and approve data" : "Open data review"}
                  </Link>
                </Button>
              )}
              {review?.status === "failed" && <CardDescription className="w-full text-loss">{review.error}</CardDescription>}
            </CardHeader>
            <CardContent className="space-y-2">
              {items.map((d) => (
                <div key={d.id} className="rounded-lg border p-2">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <FileText className="size-4 text-brand-primary" />
                    <span className="font-medium">{d.name}</span>
                    <StatusBadge status={d.status} />
                    {d.doc_type && <Badge variant="outline">{d.doc_type.replace(/_/g, " ")}</Badge>}
                    {d.pages && (
                      <span className="text-xs text-muted-foreground">
                        {d.pages} pages · {d.chunks} chunks
                      </span>
                    )}
                    {d.meta.confidence && d.meta.confidence !== "high" && (
                      <Badge variant="outline" className="text-brand-secondary">
                        <AlertTriangle className="size-3" /> {d.meta.confidence} confidence: check company/period
                      </Badge>
                    )}
                    {d.meta.corrected && <Badge variant="outline">corrected by you</Badge>}
                    <span className="ms-auto flex gap-1">
                      <Button size="icon-sm" variant="ghost" title="Correct company / period" onClick={() => setEditing(editing === d.id ? null : d.id)}>
                        <Pencil />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        title="Process again"
                        onClick={async () => {
                          await api(`/api/documents/${d.id}/reprocess`, { method: "POST" });
                          load();
                        }}
                      >
                        <RefreshCw />
                      </Button>
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        title="Delete document"
                        onClick={async () => {
                          if (!confirm(`Delete ${d.name}? It is removed from the index.`)) return;
                          await api(`/api/documents/${d.id}`, { method: "DELETE" });
                          load();
                        }}
                      >
                        <Trash2 />
                      </Button>
                    </span>
                  </div>
                  {d.error && <p className="mt-1 text-xs text-loss">{d.error}</p>}
                  {editing === d.id && (
                    <EditDoc
                      doc={d}
                      onDone={() => {
                        setEditing(null);
                        load();
                      }}
                    />
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
