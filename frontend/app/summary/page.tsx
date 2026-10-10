"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  ExternalLink,
  FileDown,
  FileText,
  Loader2,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { downloadUrl, pageExtractUrl, pdfUrl } from "@/lib/documents";
import type { Figure, Source, Summary, SummaryItem, SummaryState } from "@/lib/summary";
import { cn } from "@/lib/utils";

type Lang = "en" | "ar";

const T = {
  en: {
    issuer: "Issuer",
    auditor: "Auditor",
    board: "Board Approval",
    ai: "AI Summary",
    full: "View full analysis",
    hide: "Hide full analysis",
    copy: "Copy summary",
    copied: "Copied",
    figures: "Key Financial Figures (traceable)",
    metric: "Metric",
    change: "Change",
    source: "Source",
    implication: "Most Important Implication",
    trace: "Source Traceability",
    documents: "Full documents",
  },
  ar: {
    issuer: "الجهة المصدرة",
    auditor: "المدقق",
    board: "اعتماد مجلس الإدارة",
    ai: "ملخص الذكاء الاصطناعي",
    full: "عرض التحليل الكامل",
    hide: "إخفاء التحليل الكامل",
    copy: "نسخ الملخص",
    copied: "تم النسخ",
    figures: "الأرقام المالية الرئيسية (قابلة للتتبع)",
    metric: "البند",
    change: "التغير",
    source: "المصدر",
    implication: "أهم الدلالات",
    trace: "تتبع المصادر",
    documents: "المستندات الكاملة",
  },
};

const OPINION: Record<string, { en: string; ar: string; good: boolean }> = {
  unqualified: { en: "Unqualified", ar: "رأي غير متحفظ", good: true },
  review_conclusion: { en: "Review: no exceptions", ar: "مراجعة دون تحفظ", good: true },
  qualified: { en: "Qualified", ar: "رأي متحفظ", good: false },
  adverse: { en: "Adverse", ar: "رأي معاكس", good: false },
  disclaimer: { en: "Disclaimer", ar: "امتناع عن إبداء الرأي", good: false },
};

const sourceLabel = (s: Source) => `p.${s.page}${s.note ? `, ${s.note}` : ""}`;
const plain = (t: string) => t.replace(/\*\*/g, "");
/** "QAR'000", "QR000", "QR '000" -> "QR'000", so equal units compare equal. */
const normUnit = (u: string) =>
  u
    .replace(/\bQAR\b/i, "QR")
    .replace(/\s+/g, "")
    .replace(/[’`]/g, "'")
    .replace(/^QR'?000$/i, "QR'000");

/** Text with **bold** markers rendered as <strong>. */
function Rich({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i} className="font-semibold text-brand-ink">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

/** The first key per file + page + note, so a page is listed once. */
function uniqueKeys(keys: string[], sources: Record<string, Source>) {
  const seen = new Set<string>();
  return keys.filter((k) => {
    const s = sources[k];
    const id = s ? `${s.file}|${s.page}|${s.note ?? ""}` : "";
    if (!s || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

/** One group per item: "(p.2, p.3, p.68, Note 22)". */
function Cites({ keys, sources, active, onCite }: { keys: string[]; sources: Record<string, Source>; active: string | null; onCite: (k: string) => void }) {
  const unique = uniqueKeys(keys, sources).sort((a, b) => sources[a].page - sources[b].page);
  if (!unique.length) return null;
  return (
    <span dir="ltr" className="text-[13px] text-brand-primary">
      (
      {unique.map((k, i) => {
        const s = sources[k];
        return (
          <Fragment key={k}>
            {i > 0 && ", "}
            <button
              onClick={() => onCite(k)}
              title={`${s.file}, page ${s.page}${s.section ? ` · ${s.section}` : ""}`}
              className={cn("whitespace-nowrap underline-offset-2 hover:underline", active === k && "font-semibold underline")}
            >
              {sourceLabel(s)}
            </button>
          </Fragment>
        );
      })}
      )
    </span>
  );
}

function Unverified({ item, lang }: { item: SummaryItem; lang: Lang }) {
  const missing = item.unverified[lang] ?? [];
  if (!missing.length) return null;
  return (
    <span
      className="ms-1 inline-flex items-center gap-1 rounded bg-loss/10 px-1.5 text-[11px] text-loss"
      title="These numbers were not found in the cited passages. Check before sharing."
    >
      <AlertTriangle className="size-3" /> unverified: {missing.join(", ")}
    </span>
  );
}

function ItemText({ item, lang, sources, active, onCite }: { item: SummaryItem; lang: Lang; sources: Record<string, Source>; active: string | null; onCite: (k: string) => void }) {
  const text = item.display[lang] ?? item.display.en ?? item.en;
  return (
    <>
      <Rich text={text} />{" "}
      <Cites keys={item.citations} sources={sources} active={active} onCite={onCite} />
      <Unverified item={item} lang={lang} />
    </>
  );
}

function ChangeCell({ f }: { f: Figure }) {
  if (f.change_pct === null) return <span className="text-muted-foreground">–</span>;
  const up = f.change_pct >= 0;
  return (
    <span dir="ltr" className={cn("font-semibold", up ? "text-gain" : "text-loss")}>
      {up ? "+" : "−"}
      {Math.abs(f.change_pct).toFixed(1)}%
    </span>
  );
}

function SourcePanel({ source, onClose }: { source: Source; onClose: () => void }) {
  const isPdf = (source.path ?? source.file).toLowerCase().endsWith(".pdf");
  return (
    <Card className="sticky top-4">
      <CardHeader className="flex flex-row items-start gap-2">
        <div className="min-w-0 flex-1">
          <CardTitle className="text-base break-words">{source.file}</CardTitle>
          <p className="text-xs text-muted-foreground">
            Page {source.page}
            {source.note && ` · ${source.note}`}
            {source.section && !source.note && ` · ${source.section}`}
            {source.type === "table" && " · table"}
          </p>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close source">
          <X />
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <pre className="max-h-[55vh] overflow-auto rounded-md border bg-background/60 p-3 font-sans text-xs leading-5 whitespace-pre-wrap">
          {source.text}
        </pre>
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" variant="outline">
            <a href={pdfUrl(source)} target="_blank" rel="noreferrer">
              <ExternalLink /> Open at page {source.page}
            </a>
          </Button>
          {source.doc_id != null && isPdf && (
            <Button asChild size="sm" variant="outline">
              <a href={pageExtractUrl(source.doc_id, source.page)}>
                <FileDown /> Download page {source.page}
              </a>
            </Button>
          )}
          {source.doc_id != null && (
            <Button asChild size="sm" variant="outline">
              <a href={downloadUrl(source.doc_id)}>
                <Download /> Full PDF
              </a>
            </Button>
          )}
        </div>
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
  const [lang, setLang] = useState<Lang>("en");
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
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
    setBusy(true);
    setError(null);
    try {
      await api("/api/summary", { method: "POST", body: JSON.stringify(selected) });
      load(selected);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const copySummary = async () => {
    if (!summary) return;
    const d = summary.document;
    const text = [
      lang === "ar" ? d.title_ar || d.title_en : d.title_en,
      plain(summary.executive.display[lang] ?? summary.executive.display.en ?? ""),
      `Source: ${summary.documents.map((x) => x.file).join(", ")}`,
    ].join("\n\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const running = state?.status === "running";
  const source = activeKey && summary ? summary.sources[activeKey] : null;
  const rtl = lang === "ar";
  const t = T[lang];
  const key = selected ? `${selected.company}|${selected.period}` : "";

  // most figures share one unit; show it in the column header and only flag the exceptions
  const units = summary?.figures.map((f) => normUnit(f.unit)) ?? [];
  const mainUnit = units.sort((a, b) => units.filter((u) => u === b).length - units.filter((u) => u === a).length)[0] ?? "";
  // every source key that points at the same file + page + note (one traceability row)
  const samePlace = (k: string) => {
    if (!summary) return [];
    const s = summary.sources[k];
    return Object.keys(summary.sources).filter((o) => {
      const x = summary.sources[o];
      return x.file === s.file && x.page === s.page && (x.note ?? "") === (s.note ?? "");
    });
  };
  const usedBy = (k: string) => {
    if (!summary) return [];
    const out: string[] = [];
    summary.figures.forEach((f) => f.citations.includes(k) && out.push(lang === "ar" ? f.metric_ar || f.metric_en : f.metric_en));
    if (summary.executive.citations.includes(k)) out.push(t.ai);
    summary.implications.forEach((i) => i.citations.includes(k) && out.push(lang === "ar" ? i.title_ar || i.title_en : i.title_en));
    if (summary.document.opinion_citations.includes(k)) out.push(t.auditor);
    if (summary.document.board_citations.includes(k)) out.push(t.board);
    return out;
  };

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
              setFull(false);
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
        {summary && (
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
        )}
        <div className="ms-auto flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link href="/documents">
              <FileText /> Documents
            </Link>
          </Button>
          <Button onClick={generate} disabled={busy || running || !selected}>
            {running || busy ? <Loader2 className="animate-spin" /> : <RefreshCw />}
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
          Reading the documents: one Gemini call for the analysis, one for the Arabic. About a minute.
        </p>
      )}
      {options?.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No documents yet. Upload results documents on the <Link href="/documents" className="underline">Documents</Link> page.
        </p>
      )}
      {selected && !summary && !running && (
        <p className="text-sm text-muted-foreground">
          No summary in the current format for this period yet. Press Generate summary.
        </p>
      )}

      {summary && (
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          <div className="min-w-0 space-y-4">
            <Card>
              <CardContent lang={lang} dir={rtl ? "rtl" : "ltr"} className="space-y-7 py-6">
                {/* document header */}
                <div className="space-y-3">
                  <h2 className="text-2xl leading-tight font-bold text-brand-primary">
                    {rtl ? summary.document.title_ar || summary.document.title_en : summary.document.title_en}
                  </h2>
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                    <span>
                      <span className="text-muted-foreground">{t.issuer}:</span>{" "}
                      <strong>{rtl ? summary.document.issuer_ar || summary.document.issuer_en : summary.document.issuer_en}</strong>
                    </span>
                    {summary.document.auditor && (
                      <span>
                        <span className="text-muted-foreground">{t.auditor}:</span> <strong dir="ltr">{summary.document.auditor}</strong>
                        {!summary.document.auditor_verified && (
                          <span title="The auditor's name was not found in the cited passages. Check the document." className="ms-1 inline-flex align-middle text-loss">
                            <AlertTriangle className="size-3.5" />
                          </span>
                        )}
                      </span>
                    )}
                    {OPINION[summary.document.opinion] && (
                      <button
                        onClick={() => summary.document.opinion_citations[0] && setActiveKey(summary.document.opinion_citations[0])}
                        title="Auditor's opinion: click to see the passage"
                        className={cn(
                          "rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide uppercase",
                          OPINION[summary.document.opinion].good
                            ? "border-gain/30 bg-gain/10 text-gain"
                            : "border-loss/30 bg-loss/10 text-loss",
                        )}
                      >
                        {OPINION[summary.document.opinion][lang]}
                      </button>
                    )}
                    {summary.document.board_approval && (
                      <span>
                        <span className="text-muted-foreground">{t.board}:</span>{" "}
                        <button
                          className="font-semibold hover:underline"
                          onClick={() => summary.document.board_citations[0] && setActiveKey(summary.document.board_citations[0])}
                        >
                          {summary.document.board_approval}
                        </button>
                      </span>
                    )}
                  </div>
                </div>

                {/* AI summary */}
                <div className="space-y-4 rounded-lg border border-brand-primary/20 bg-brand-primary/5 p-5">
                  <span className="inline-block rounded bg-brand-primary px-2.5 py-1 text-xs font-semibold tracking-wide text-white uppercase">
                    {t.ai}
                  </span>
                  <p className="leading-7">
                    <ItemText item={summary.executive} lang={lang} sources={summary.sources} active={activeKey} onCite={setActiveKey} />
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <Button onClick={() => setFull((v) => !v)}>
                      {full ? t.hide : t.full}
                      {full ? <ChevronDown /> : <ChevronRight className="rtl:rotate-180" />}
                    </Button>
                    <Button variant="outline" onClick={copySummary}>
                      {copied ? <Check /> : <Copy />} {copied ? t.copied : t.copy}
                    </Button>
                  </div>
                  {full && (
                    <div className="space-y-5 border-t border-brand-primary/15 pt-4">
                      {summary.sections.map((s, si) => (
                        <section key={si} className="space-y-2">
                          <h3 className="font-semibold text-brand-primary">{rtl ? s.title_ar || s.title_en : s.title_en}</h3>
                          <ul className="list-disc space-y-1.5 ps-5 text-sm leading-6">
                            {s.points.map((p, pi) => (
                              <li key={pi}>
                                <ItemText item={p} lang={lang} sources={summary.sources} active={activeKey} onCite={setActiveKey} />
                              </li>
                            ))}
                          </ul>
                        </section>
                      ))}
                    </div>
                  )}
                </div>

                {/* key figures */}
                {summary.figures.length > 0 && (
                  <section className="space-y-3">
                    <h3 className="text-lg font-semibold text-brand-primary">{t.figures}</h3>
                    <div className="overflow-x-auto rounded-lg border">
                      <table className="w-full text-sm">
                        <thead className="bg-muted/50 text-xs text-muted-foreground">
                          <tr>
                            <th className="px-3 py-2.5 text-start font-medium">{t.metric}</th>
                            <th className="px-3 py-2.5 text-end font-medium" dir="ltr">
                              {summary.period_labels.current} {mainUnit && `(${mainUnit})`}
                            </th>
                            <th className="px-3 py-2.5 text-end font-medium" dir="ltr">
                              {summary.period_labels.prior} {mainUnit && `(${mainUnit})`}
                            </th>
                            <th className="px-3 py-2.5 text-end font-medium">{t.change}</th>
                            <th className="px-3 py-2.5 text-end font-medium">{t.source}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {summary.figures.map((f) => {
                            const s = summary.sources[f.citations[0]];
                            return (
                              <tr key={f.id} className="border-t">
                                <td className="px-3 py-2.5">
                                  {rtl ? f.metric_ar || f.metric_en : f.metric_en}
                                  {normUnit(f.unit) !== mainUnit && <span className="ms-1 text-xs text-muted-foreground">({normUnit(f.unit)})</span>}
                                  {!f.verified && (
                                    <span title={f.issues.join("; ")} className="ms-1 inline-flex align-middle text-loss">
                                      <AlertTriangle className="size-3.5" />
                                    </span>
                                  )}
                                </td>
                                <td className="px-3 py-2.5 text-end tabular-nums" dir="ltr">
                                  <button
                                    onClick={() => f.citations[0] && setActiveKey(f.citations[0])}
                                    className="text-brand-primary underline underline-offset-2"
                                    title="Show the passage this figure is copied from"
                                  >
                                    {f.current}
                                  </button>
                                </td>
                                <td className="px-3 py-2.5 text-end tabular-nums" dir="ltr">
                                  {f.prior || "–"}
                                </td>
                                <td className="px-3 py-2.5 text-end tabular-nums">
                                  <ChangeCell f={f} />
                                </td>
                                <td className="px-3 py-2.5 text-end whitespace-nowrap" dir="ltr">
                                  {s ? (
                                    <button onClick={() => setActiveKey(f.citations[0])} className="text-brand-primary underline underline-offset-2">
                                      {sourceLabel(s)}
                                    </button>
                                  ) : (
                                    "–"
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Values are copied exactly as printed and checked against the cited page; changes are computed in Python.
                    </p>
                  </section>
                )}

                {/* implications */}
                {summary.implications.length > 0 && (
                  <section className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-5 dark:border-amber-700/60 dark:bg-amber-950/30">
                    <h3 className="flex items-center gap-2 text-sm font-bold tracking-wide text-amber-800 uppercase dark:text-amber-300">
                      <AlertTriangle className="size-4" /> {t.implication}
                    </h3>
                    <ul className="list-disc space-y-2 ps-5 text-sm leading-6">
                      {summary.implications.map((imp, i) => (
                        <li key={i}>
                          <strong>{rtl ? imp.title_ar || imp.title_en : imp.title_en}:</strong>{" "}
                          <ItemText item={imp} lang={lang} sources={summary.sources} active={activeKey} onCite={setActiveKey} />
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {/* traceability */}
                <section className="space-y-3">
                  <h3 className="text-lg font-semibold text-brand-primary">{t.trace}</h3>
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50 text-xs text-muted-foreground">
                        <tr>
                          <th className="px-3 py-2 text-start font-medium">Page / Note</th>
                          <th className="px-3 py-2 text-start font-medium">Section</th>
                          <th className="px-3 py-2 text-start font-medium">Used for</th>
                          <th className="px-3 py-2 text-end font-medium">Download</th>
                        </tr>
                      </thead>
                      <tbody>
                        {uniqueKeys(Object.keys(summary.sources), summary.sources)
                          .map((k) => [k, summary.sources[k]] as const)
                          .sort(([, a], [, b]) => a.file.localeCompare(b.file) || a.page - b.page)
                          .map(([k, s]) => (
                            <tr key={k} className={cn("border-t", activeKey === k && "bg-brand-primary/5")}>
                              <td className="px-3 py-2 whitespace-nowrap" dir="ltr">
                                <button onClick={() => setActiveKey(k)} className="text-brand-primary underline underline-offset-2">
                                  {sourceLabel(s)}
                                </button>
                                {summary.documents.length > 1 && (
                                  <span className="block text-[11px] text-muted-foreground">{s.file}</span>
                                )}
                              </td>
                              <td className="px-3 py-2 text-xs text-muted-foreground" dir="ltr">
                                {s.section || "–"}
                              </td>
                              <td className="px-3 py-2 text-xs">
                                {[...new Set(samePlace(k).flatMap(usedBy))].join(", ") || "–"}
                              </td>
                              <td className="px-3 py-2 text-end whitespace-nowrap">
                                {s.doc_id != null && (s.path ?? s.file).toLowerCase().endsWith(".pdf") && (
                                  <a
                                    href={pageExtractUrl(s.doc_id, s.page)}
                                    className="inline-flex items-center gap-1 text-xs text-brand-primary hover:underline"
                                    title={`Download page ${s.page} as PDF`}
                                  >
                                    <FileDown className="size-3.5" /> p.{s.page}
                                  </a>
                                )}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                {/* full documents */}
                <section className="space-y-2">
                  <h3 className="text-lg font-semibold text-brand-primary">{t.documents}</h3>
                  <div className="flex flex-wrap gap-3">
                    {summary.documents.map((d) => (
                      <div key={d.id} className="flex items-center gap-3 rounded-lg border bg-background/60 px-3 py-2">
                        <FileText className="size-5 text-brand-primary" />
                        <div className="min-w-0 text-sm" dir="ltr">
                          <div className="max-w-[22rem] truncate font-medium" title={d.file}>
                            {d.file}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {d.pages ? `${d.pages} pages · ` : ""}
                            {d.size_kb.toLocaleString()} KB
                          </div>
                        </div>
                        <Button asChild size="sm">
                          <a href={downloadUrl(d.id)}>
                            <Download /> PDF
                          </a>
                        </Button>
                      </div>
                    ))}
                  </div>
                </section>
              </CardContent>
            </Card>
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span
                className={cn(
                  "inline-flex items-center gap-1",
                  summary.checks.figures_verified === summary.checks.figures && summary.checks.verified === summary.checks.bullets
                    ? "text-gain"
                    : "text-brand-ink",
                )}
              >
                <ShieldCheck className="size-3.5" />
                {summary.checks.figures_verified}/{summary.checks.figures} figures found on the cited page ·{" "}
                {summary.checks.verified}/{summary.checks.bullets} statements with every number in the cited source
              </span>
              <span>
                Generated {new Date(summary.generated_at).toLocaleString()} by {summary.model}. AI-generated summary;
                the full document prevails.
              </span>
            </p>
          </div>

          <aside>
            {source ? (
              <SourcePanel source={source} onClose={() => setActiveKey(null)} />
            ) : (
              <Card className="sticky top-4">
                <CardContent className="py-6 text-sm text-muted-foreground">
                  Click any figure or page reference such as <span className="text-brand-primary underline">p.7</span> to see the
                  exact passage, open the PDF at that page, download that page, or download the full document.
                </CardContent>
              </Card>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
