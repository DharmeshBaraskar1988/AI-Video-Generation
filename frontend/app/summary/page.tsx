"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ExternalLink, FileText, Loader2, RefreshCw, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { pdfUrl } from "@/lib/documents";
import type { Source, Summary, SummaryItem, SummaryState } from "@/lib/summary";
import { cn } from "@/lib/utils";

type View = "executive" | "investor";
type Lang = "en" | "ar";

const shortName = (file: string) => file.replace(/\.pdf$/i, "");

function Citation({ source, active, onClick }: { source?: Source; active: boolean; onClick: () => void }) {
  if (!source) return null;
  return (
    <button
      onClick={onClick}
      title={`${source.file}, page ${source.page}${source.section ? ` · ${source.section}` : ""}`}
      className={cn(
        "mx-0.5 inline-flex items-center rounded border px-1.5 align-baseline text-[11px] leading-5 whitespace-nowrap",
        active
          ? "border-brand-primary bg-brand-primary text-white"
          : "border-brand-primary/30 bg-brand-primary/5 text-brand-primary hover:bg-brand-primary/15",
      )}
      dir="ltr"
    >
      [{shortName(source.file)} p.{source.page}]
    </button>
  );
}

function Bullet({
  item,
  lang,
  sources,
  activeKey,
  onCite,
}: {
  item: SummaryItem;
  lang: Lang;
  sources: Record<string, Source>;
  activeKey: string | null;
  onCite: (k: string) => void;
}) {
  const text = lang === "ar" ? item.ar ?? item.en : item.en;
  const missing = item.unverified[lang] ?? [];
  return (
    <li className="leading-7">
      <span>{text}</span>{" "}
      {item.citations.map((k) => (
        <Citation key={k} source={sources[k]} active={activeKey === k} onClick={() => onCite(k)} />
      ))}
      {missing.length > 0 && (
        <span
          className="ms-1 inline-flex items-center gap-1 rounded bg-loss/10 px-1.5 text-[11px] text-loss"
          title="These numbers were not found in the cited passages. Check before sharing."
        >
          <AlertTriangle className="size-3" /> unverified: {missing.join(", ")}
        </span>
      )}
    </li>
  );
}

function SourcePanel({ source, onClose }: { source: Source; onClose: () => void }) {
  const pdf = pdfUrl(source);
  return (
    <Card className="sticky top-4">
      <CardHeader className="flex flex-row items-start gap-2">
        <div className="min-w-0 flex-1">
          <CardTitle className="text-base break-words">{source.file}</CardTitle>
          <p className="text-xs text-muted-foreground">
            Page {source.page}
            {source.section && ` · ${source.section}`}
            {source.type === "table" && " · table"}
          </p>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close source">
          <X />
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <pre className="max-h-[60vh] overflow-auto rounded-md border bg-background/60 p-3 font-sans text-xs leading-5 whitespace-pre-wrap">
          {source.text}
        </pre>
        <Button asChild size="sm" variant="outline">
          <a href={pdf} target="_blank" rel="noreferrer">
            <ExternalLink /> Open PDF at page {source.page}
          </a>
        </Button>
      </CardContent>
    </Card>
  );
}

type Option = { company: string; period: string; name_en: string; name_ar: string; has_summary: boolean; state: SummaryState };
type SummaryResponse = { options: Option[]; company: string | null; period: string | null; state: SummaryState; summary: Summary | null };

export default function SummaryPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [state, setState] = useState<SummaryState | null>(null);
  const [options, setOptions] = useState<Option[] | null>(null);
  const [selected, setSelected] = useState<{ company: string; period: string } | null>(null);
  const [view, setView] = useState<View>("executive");
  const [lang, setLang] = useState<Lang>("en");
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [busy, setBusy] = useState<"generate" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const load = useCallback((pick?: { company: string; period: string }) => {
    clearTimeout(timer.current);
    const q = pick ? `?company=${encodeURIComponent(pick.company)}&period=${encodeURIComponent(pick.period)}` : "";
    api<SummaryResponse>(`/api/summary${q}`)
      .then((d) => {
        setOptions(d.options);
        setState(d.state);
        setSummary(d.summary);
        if (d.company && d.period) setSelected({ company: d.company, period: d.period });
        if (d.state.status === "running" && d.company && d.period)
          timer.current = setTimeout(() => load({ company: d.company!, period: d.period! }), 3000);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    load();
    return () => clearTimeout(timer.current);
  }, [load]);

  const generate = async () => {
    if (!selected) return;
    setBusy("generate");
    setError(null);
    try {
      await api("/api/summary", { method: "POST", body: JSON.stringify(selected) });
      load(selected);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const running = state?.status === "running";
  const source = activeKey && summary ? summary.sources[activeKey] : null;
  const rtl = lang === "ar";
  const key = selected ? `${selected.company}|${selected.period}` : "";

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-brand-primary">Summary</h1>
        {options && options.length > 0 && (
          <select
            value={key}
            onChange={(e) => {
              const [company, period] = e.target.value.split("|");
              setActiveKey(null);
              load({ company, period });
            }}
            className="h-9 rounded-md border bg-card px-2 text-sm"
          >
            {options.map((o) => (
              <option key={`${o.company}|${o.period}`} value={`${o.company}|${o.period}`}>
                {o.name_en} · {o.period}
                {o.has_summary ? "" : " (no summary yet)"}
              </option>
            ))}
          </select>
        )}
        <div className="ms-auto flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link href="/documents">
              <FileText /> Documents
            </Link>
          </Button>
          <Button onClick={generate} disabled={busy !== null || running || !selected}>
            {running || busy === "generate" ? <Loader2 className="animate-spin" /> : <RefreshCw />}
            {summary ? "Regenerate summary" : "Generate summary"}
          </Button>
        </div>
      </header>

      {error && <p className="rounded-md border border-loss/40 bg-loss/5 p-2 text-sm text-loss">{error}</p>}
      {state?.status === "failed" && (
        <p className="rounded-md border border-loss/40 bg-loss/5 p-2 text-sm text-loss">Summary failed: {state.error}</p>
      )}
      {running && (
        <p className="text-sm text-muted-foreground">
          Writing the summary: one Gemini call per section, then the executive summary. About a minute.
        </p>
      )}
      {options?.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No documents yet. Upload results documents on the <Link href="/documents" className="underline">Documents</Link> page.
        </p>
      )}
      {selected && !summary && !running && (
        <p className="text-sm text-muted-foreground">No summary for this period yet. Press Generate summary.</p>
      )}

      {summary && (
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          <div className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex rounded-lg border bg-card p-0.5">
                {(["executive", "investor"] as View[]).map((v) => (
                  <button
                    key={v}
                    onClick={() => setView(v)}
                    className={cn(
                      "rounded-md px-3 py-1 text-sm font-medium capitalize",
                      v === view ? "bg-brand-primary text-white" : "text-muted-foreground hover:text-brand-ink",
                    )}
                  >
                    {v}
                  </button>
                ))}
              </div>
              <div className="inline-flex rounded-lg border bg-card p-0.5">
                {(["en", "ar"] as Lang[]).map((l) => (
                  <button
                    key={l}
                    onClick={() => setLang(l)}
                    className={cn(
                      "rounded-md px-3 py-1 text-sm font-medium",
                      l === lang ? "bg-brand-primary text-white" : "text-muted-foreground hover:text-brand-ink",
                    )}
                  >
                    {l === "en" ? "English" : "العربية"}
                  </button>
                ))}
              </div>
              <span
                className={cn(
                  "ms-auto inline-flex items-center gap-1 text-sm",
                  summary.checks.verified === summary.checks.bullets ? "text-gain" : "text-brand-ink",
                )}
              >
                <ShieldCheck className="size-4" />
                {summary.checks.verified}/{summary.checks.bullets} points: every number found in the cited source
              </span>
            </div>

            <Card>
              <CardHeader>
                <CardTitle lang={lang} dir={rtl ? "rtl" : "ltr"} className="text-xl text-brand-primary">
                  {rtl ? summary.title_ar : summary.title_en}
                </CardTitle>
              </CardHeader>
              <CardContent lang={lang} dir={rtl ? "rtl" : "ltr"} className="space-y-6">
                {view === "executive" ? (
                  <ul className="list-disc space-y-2 ps-5">
                    {summary.executive.map((item, i) => (
                      <Bullet key={i} item={item} lang={lang} sources={summary.sources} activeKey={activeKey} onCite={setActiveKey} />
                    ))}
                  </ul>
                ) : (
                  summary.sections.map((s) => (
                    <section key={s.id} className="space-y-2">
                      <h3 className="font-semibold text-brand-primary">{rtl ? s.title_ar : s.title_en}</h3>
                      <ul className="list-disc space-y-2 ps-5">
                        {s.points.map((item, i) => (
                          <Bullet key={i} item={item} lang={lang} sources={summary.sources} activeKey={activeKey} onCite={setActiveKey} />
                        ))}
                      </ul>
                    </section>
                  ))
                )}
              </CardContent>
            </Card>
            <p className="text-xs text-muted-foreground">
              Generated {new Date(summary.generated_at).toLocaleString()} by {summary.model} from{" "}
              {summary.documents.map((d) => d.file).join(", ")}. Click a citation to see the passage it comes from.
            </p>
          </div>

          <aside>
            {source ? (
              <SourcePanel source={source} onClose={() => setActiveKey(null)} />
            ) : (
              <Card>
                <CardContent className="py-6 text-sm text-muted-foreground">
                  Click a citation such as <span className="rounded border px-1 text-brand-primary">[file p.4]</span> to see
                  the exact passage and open the PDF at that page.
                </CardContent>
              </Card>
            )}
          </aside>
        </div>
      )}

    </div>
  );
}
