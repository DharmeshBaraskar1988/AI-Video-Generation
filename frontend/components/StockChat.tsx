"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Brain,
  Building2,
  ChartLine,
  Clock,
  CornerDownRight,
  ExternalLink,
  FileText,
  Globe,
  Loader2,
  MessageSquarePlus,
  Newspaper,
  Send,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { API_URL, api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Quote = {
  symbol: string;
  price: number;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  currency: string;
  as_of: string;
  as_of_hhmm: string;
  as_of_date: string;
  market_open: boolean;
  delayed: boolean;
};

type History = {
  symbol: string;
  days: number;
  start_date: string;
  end_date: string;
  change: number;
  change_pct: number | null;
  closes: { date: string; close: number }[];
};

type Profile = {
  symbol: string;
  url: string;
  name?: string;
  website?: string;
  sector?: string;
  industry?: string;
  city?: string;
  employees?: string;
  summary?: string;
  market_cap?: string;
  pe_trailing?: string;
  eps_trailing?: string;
  dividend_per_share?: string;
  dividend_yield?: string;
  price_to_book?: string;
  week52_range?: string;
  avg_50d?: string;
  avg_200d?: string;
  revenue_ttm?: string;
  net_income_ttm?: string;
};

type EvidenceKind = "price" | "profile" | "document" | "news" | "web";
type Evidence = {
  label: string;
  kind: EvidenceKind;
  title: string;
  subtitle: string;
  url: string | null;
  snippet: string;
  cited: boolean;
};

type Memory = { summary: string; recent_turns: number; older_turns: number };

type Reply = {
  question: string;
  standalone: string | null;
  relation: "first" | "follow_up" | "earlier" | "new" | null;
  scope?: "in_scope" | "off_topic";
  intents?: string[];
  profiles?: Profile[];
  evidence?: Evidence[];
  memory_model: string | null;
  lang: "en" | "ar";
  ok: boolean;
  answer: string;
  source_line: string;
  answer_by: "llm" | "template" | "fallback";
  model: string | null;
  companies: { symbol: string; name_en: string; name_ar: string }[];
  quotes: Quote[];
  histories: History[];
  memory?: Memory;
};

type Message = { role: "user"; text: string } | { role: "bot"; reply: Reply } | { role: "error"; text: string };

const EXAMPLES = {
  en: [
    "Tell me about QNB",
    "What was QNB's net profit in Q1 2026?",
    "What is Industries Qatar trading at?",
    "Compare QNB and Ooredoo over the last 3 months",
    "Why did Industries Qatar fall this week?",
    "What is a P/E ratio?",
    "Latest Qatar stock market news",
  ],
  ar: [
    "أخبرني عن بنك قطر الوطني",
    "كم سعر سهم صناعات قطر؟",
    "ما أداء بنك قطر الوطني خلال الشهر الماضي؟",
    "لماذا انخفض سهم صناعات قطر هذا الأسبوع؟",
  ],
};

const SESSION_KEY = "stockChatSession";
const RELATION_LABEL: Record<string, string> = {
  follow_up: "Follow-up",
  earlier: "From earlier in the chat",
  new: "New topic",
};

function newSessionId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

const KIND: Record<EvidenceKind, { icon: typeof FileText; label: string; chip: string }> = {
  price: { icon: ChartLine, label: "Price", chip: "border-brand-primary/40 bg-brand-primary/10 text-brand-primary" },
  profile: { icon: Building2, label: "Company", chip: "border-brand-secondary/40 bg-brand-secondary/10 text-brand-secondary" },
  document: { icon: FileText, label: "Document", chip: "border-gain/40 bg-gain/10 text-gain" },
  news: { icon: Newspaper, label: "News", chip: "border-brand-accent/60 bg-brand-accent/15 text-brand-ink" },
  web: { icon: Globe, label: "Web", chip: "border-brand-primary/30 bg-muted text-brand-primary" },
};
const INTENT_LABEL: Record<string, string> = {
  price: "Price",
  performance: "Performance",
  profile: "Company profile",
  documents: "Uploaded documents",
  news: "News",
  concept: "Finance concept",
  web: "Web search",
  sources: "Previous answer's sources",
};

const href = (url: string | null) => (!url ? undefined : url.startsWith("/") ? `${API_URL}${url}` : url);
const evidenceId = (msg: number, label: string) => `ev-${msg}-${label}`;

function focusEvidence(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  el.classList.add("ring-2", "ring-brand-accent");
  setTimeout(() => el.classList.remove("ring-2", "ring-brand-accent"), 1500);
}

/** Answer text with [D1]-style labels turned into clickable chips; "- " lines become a list. */
function AnswerText({ text, evidence, msg }: { text: string; evidence: Evidence[]; msg: number }) {
  const byLabel = new Map(evidence.map((e) => [e.label, e]));
  const inline = (line: string) =>
    line.split(/(\[[QCDNWP]\d+\])/g).map((part, i) => {
      const label = part.match(/^\[([QCDNWP]\d+)\]$/)?.[1];
      if (!label)
        return (
          <span key={i}>
            {part.split(/(https?:\/\/[^\s)\]]+[^\s)\].,;:])/g).map((piece, j) =>
              /^https?:\/\//.test(piece) ? (
                <a key={j} href={piece} target="_blank" rel="noreferrer" className="break-all text-brand-primary underline">
                  {piece}
                </a>
              ) : (
                piece
              ),
            )}
          </span>
        );
      const ev = byLabel.get(label);
      if (!ev) return null;
      return (
        <button
          key={i}
          type="button"
          onClick={() => focusEvidence(evidenceId(msg, label))}
          title={ev.title}
          className={cn("mx-0.5 inline-flex h-5 items-center rounded border px-1 align-baseline text-[10px] font-semibold", KIND[ev.kind].chip)}
        >
          {label}
        </button>
      );
    });
  const lines = text.split("\n").filter((l) => l.trim());
  const isBullet = (l: string) => /^\s*[-•]\s/.test(l);
  return (
    <div className="space-y-2">
      {lines
        .filter((l) => !isBullet(l))
        .map((l, i) => (
          <p key={i}>{inline(l)}</p>
        ))}
      {lines.some(isBullet) && (
        <ul className="list-disc space-y-1 ps-5">
          {lines.filter(isBullet).map((l, i) => (
            <li key={i}>{inline(l.replace(/^\s*[-•]\s/, ""))}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div className="rounded-md bg-muted/50 px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="tabular text-sm font-semibold">{value}</div>
    </div>
  );
}

function ProfileCard({ p }: { p: Profile }) {
  return (
    <div className="rounded-xl border bg-card p-4 shadow-sm" dir="ltr">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Building2 className="size-4 text-brand-secondary" />
            <span className="font-semibold">{p.name ?? p.symbol}</span>
            <Badge variant="outline">{p.symbol}</Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {[p.sector, p.industry, p.city, p.employees && `${p.employees} employees`].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {p.website && (
            <Button variant="outline" size="sm" asChild>
              <a href={p.website} target="_blank" rel="noreferrer">
                <Globe /> {p.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
              </a>
            </Button>
          )}
          <Button variant="outline" size="sm" asChild>
            <a href={p.url} target="_blank" rel="noreferrer">
              <ExternalLink /> Yahoo Finance
            </a>
          </Button>
        </div>
      </div>
      {p.summary && (
        <details className="group mt-3 text-sm text-muted-foreground">
          <summary className="cursor-pointer list-none group-open:hidden">
            <span className="line-clamp-2">{p.summary}</span>
            <span className="text-xs text-brand-primary">Show more</span>
          </summary>
          <p>{p.summary}</p>
        </details>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Market cap" value={p.market_cap} />
        <Stat label="P/E (TTM)" value={p.pe_trailing} />
        <Stat label="EPS (TTM)" value={p.eps_trailing} />
        <Stat label="Dividend yield" value={p.dividend_yield} />
        <Stat label="Dividend / share" value={p.dividend_per_share} />
        <Stat label="Price / book" value={p.price_to_book} />
        <Stat label="52-week range" value={p.week52_range} />
        <Stat label="50 / 200-day avg" value={p.avg_50d && p.avg_200d ? `${p.avg_50d} / ${p.avg_200d}` : undefined} />
        <Stat label="Revenue (TTM)" value={p.revenue_ttm} />
        <Stat label="Net income (TTM)" value={p.net_income_ttm} />
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">Company data from Yahoo Finance; figures may lag the latest filings.</p>
    </div>
  );
}

function EvidenceCard({ e, id }: { e: Evidence; id: string }) {
  const k = KIND[e.kind];
  const Icon = k.icon;
  const link = href(e.url);
  return (
    <div id={id} className={cn("flex gap-3 rounded-lg border bg-card p-3 transition-shadow", !e.cited && "opacity-70")} dir="auto">
      <div className={cn("flex size-8 shrink-0 items-center justify-center rounded-md border", k.chip)}>
        <Icon className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span className={cn("rounded border px-1 font-semibold", k.chip)}>{e.label}</span>
          <span>{k.label}</span>
          {!e.cited && <span>· related</span>}
        </div>
        {link ? (
          <a href={link} target="_blank" rel="noreferrer" className="mt-0.5 line-clamp-2 text-sm font-medium break-words hover:underline">
            {e.title} <ExternalLink className="inline size-3 opacity-60" />
          </a>
        ) : (
          <p className="mt-0.5 line-clamp-2 text-sm font-medium">{e.title}</p>
        )}
        {e.subtitle && <p className="text-xs text-muted-foreground">{e.subtitle}</p>}
        {e.snippet && e.kind !== "price" && (
          <p className="mt-1 line-clamp-3 border-s-2 ps-2 text-xs italic text-muted-foreground">{e.snippet}</p>
        )}
      </div>
    </div>
  );
}

const signed = (x: number | null, d: number) => (x === null ? "n/a" : `${x > 0 ? "+" : ""}${x.toFixed(d)}`);

function Sparkline({ closes, up }: { closes: { close: number }[]; up: boolean }) {
  if (closes.length < 2) return null;
  const w = 160;
  const h = 40;
  const vals = closes.map((c) => c.close);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const pts = vals
    .map((v, i) => `${(i / (vals.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * (h - 4) - 2}`)
    .join(" ");
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={pts} fill="none" strokeWidth={2} className={up ? "stroke-gain" : "stroke-loss"} />
    </svg>
  );
}

function QuoteCard({ q, name, history }: { q: Quote; name: string; history?: History }) {
  const up = (q.change ?? 0) >= 0;
  return (
    <div className="min-w-56 flex-1 rounded-lg border bg-card p-3" dir="ltr">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium">{name}</span>
        <span className="text-xs text-muted-foreground">{q.symbol}</span>
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="tabular text-2xl font-semibold">{q.price.toFixed(3)}</span>
        <span className="text-xs text-muted-foreground">{q.currency}</span>
        <span className={cn("tabular ms-auto inline-flex items-center text-sm font-medium", up ? "text-gain" : "text-loss")}>
          {up ? <ArrowUpRight className="size-4" /> : <ArrowDownRight className="size-4" />}
          {signed(q.change, 3)} ({signed(q.change_pct, 2)}%)
        </span>
      </div>
      {history && (
        <div className="mt-2 flex items-end justify-between gap-2">
          <Sparkline closes={history.closes} up={history.change >= 0} />
          <span className={cn("tabular text-xs", history.change >= 0 ? "text-gain" : "text-loss")}>
            {history.days}d {signed(history.change_pct, 2)}%
          </span>
        </div>
      )}
    </div>
  );
}

function OffTopic({ reply, onAsk }: { reply: Reply; onAsk: (q: string) => void }) {
  const rtl = reply.lang === "ar";
  return (
    <div className="space-y-2">
      <div
        dir={rtl ? "rtl" : "ltr"}
        lang={reply.lang}
        className="flex gap-3 rounded-2xl rounded-ss-sm border border-dashed bg-muted/40 px-4 py-3 text-sm leading-6"
      >
        <ShieldAlert className="mt-0.5 size-5 shrink-0 text-brand-secondary" />
        <div>
          <p className="font-medium">{rtl ? "خارج نطاق المساعد المالي" : "Outside this assistant's scope"}</p>
          <p className="text-muted-foreground">{reply.answer}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5" dir={rtl ? "rtl" : "ltr"}>
        {EXAMPLES[reply.lang].slice(0, 3).map((ex) => (
          <button
            key={ex}
            onClick={() => onAsk(ex)}
            className="rounded-full border bg-card px-3 py-1 text-xs text-brand-primary hover:bg-sidebar-accent"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

function BotMessage({ reply, msg, onAsk }: { reply: Reply; msg: number; onAsk: (q: string) => void }) {
  const rtl = reply.lang === "ar";
  const q0 = reply.quotes[0];
  const evidence = reply.evidence ?? [];
  const sources = evidence.filter((e) => e.kind !== "price" || e.label.startsWith("P")).sort((a, b) => Number(b.cited) - Number(a.cited));
  if (reply.scope === "off_topic") return <OffTopic reply={reply} onAsk={onAsk} />;
  const label = reply.relation ? RELATION_LABEL[reply.relation] : undefined;
  return (
    <div className="space-y-2">
      {label && (
        <p className="flex items-center gap-1 text-xs text-muted-foreground" title={reply.memory_model ?? undefined}>
          <CornerDownRight className="size-3" />
          <span className="font-medium">{label}</span>
          {reply.standalone && (
            <span dir="auto" className="truncate">
              · understood as “{reply.standalone}”
            </span>
          )}
        </p>
      )}
      <div
        dir={rtl ? "rtl" : "ltr"}
        lang={reply.lang}
        className={cn(
          "rounded-2xl rounded-ss-sm border bg-card px-4 py-3 text-sm leading-6 shadow-sm",
          !reply.ok && "border-brand-accent/60 bg-brand-accent/10",
        )}
      >
        {!reply.ok && <TriangleAlert className="me-1 inline size-4 text-brand-secondary" />}
        <AnswerText text={reply.answer} evidence={evidence} msg={msg} />
        {reply.source_line && <p className="mt-2 border-t pt-2 text-xs text-muted-foreground">{reply.source_line}</p>}
      </div>
      {reply.profiles?.map((p) => <ProfileCard key={p.symbol} p={p} />)}
      {reply.quotes.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {reply.quotes.map((q, i) => (
            <QuoteCard
              key={q.symbol}
              q={q}
              name={rtl ? reply.companies[i]?.name_ar : reply.companies[i]?.name_en}
              history={reply.histories.find((h) => h.symbol === q.symbol)}
            />
          ))}
        </div>
      )}
      {sources.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">
            Evidence · {sources.filter((e) => e.cited).length} cited of {sources.length}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {sources.map((e) => (
              <EvidenceCard key={e.label} e={e} id={evidenceId(msg, e.label)} />
            ))}
          </div>
        </div>
      )}
      {(reply.intents?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          Checked:
          {reply.intents!.map((i) => (
            <Badge key={i} variant="secondary" className="text-[11px]">
              {INTENT_LABEL[i] ?? i}
            </Badge>
          ))}
        </div>
      )}
      {q0 && (
        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline" className="gap-1">
            <Clock className="size-3" /> {q0.as_of_hhmm} Doha · {q0.as_of_date}
          </Badge>
          {q0.delayed && <Badge variant="outline">Delayed</Badge>}
          <Badge variant="outline" className={q0.market_open ? "text-gain" : "text-brand-secondary"}>
            {q0.market_open ? "Market open" : "Market closed"}
          </Badge>
          <Badge variant="outline" className="text-muted-foreground">
            {reply.answer_by === "llm" ? `Worded by ${reply.model}` : "Template answer"}
          </Badge>
        </div>
      )}
    </div>
  );
}

export function StockChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [lang, setLang] = useState<"en" | "ar">("en");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [memory, setMemory] = useState<Memory | null>(null);
  const end = useRef<HTMLDivElement>(null);

  // One conversation per browser; restore it after a reload.
  useEffect(() => {
    let id: string | null = null;
    try {
      id = localStorage.getItem(SESSION_KEY);
    } catch {}
    if (!id) {
      id = newSessionId();
      try {
        localStorage.setItem(SESSION_KEY, id);
      } catch {}
      setSessionId(id);
      return;
    }
    setSessionId(id);
    api<{ turns: Reply[]; memory: Memory }>(`/api/stock/session/${id}`)
      .then((h) => {
        setMessages(h.turns.flatMap((t): Message[] => [{ role: "user", text: t.question }, { role: "bot", reply: t }]));
        setMemory(h.memory);
      })
      .catch(() => {});
  }, []);

  const newChat = () => {
    if (busy) return;
    if (sessionId) void api(`/api/stock/session/${sessionId}`, { method: "DELETE" }).catch(() => {});
    const id = newSessionId();
    try {
      localStorage.setItem(SESSION_KEY, id);
    } catch {}
    setSessionId(id);
    setMessages([]);
    setMemory(null);
  };

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (q: string) => {
    const question = q.trim();
    if (!question || busy) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setText("");
    setBusy(true);
    try {
      const reply = await api<Reply>("/api/stock/chat", {
        method: "POST",
        body: JSON.stringify({ question, session_id: sessionId }),
      });
      setMessages((m) => [...m, { role: "bot", reply }]);
      if (reply.memory) setMemory(reply.memory);
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: (e as Error).message }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col gap-4">
      {messages.length > 0 && (
        <div className="flex items-start gap-2">
          <details className="flex-1 rounded-lg border bg-card px-3 py-2 text-xs text-muted-foreground">
            <summary className="flex cursor-pointer items-center gap-1.5">
              <Brain className="size-3.5" />
              Memory: last {memory?.recent_turns ?? 0} turns of this topic
              {memory?.older_turns ? ` · ${memory.older_turns} older turns` : ""}
              {memory?.summary ? " · long-term summary" : ""}
            </summary>
            <p className="mt-2 whitespace-pre-line">
              {memory?.summary ||
                "No long-term summary yet. Older turns are summarised once the conversation grows. Prices are always fetched again, never taken from memory."}
            </p>
          </details>
          <Button variant="outline" size="sm" onClick={newChat} disabled={busy}>
            <MessageSquarePlus /> New chat
          </Button>
        </div>
      )}
      <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border bg-background/50 p-4">
        {messages.length === 0 && (
          <div className="space-y-3 py-6 text-center">
            <p className="text-sm text-muted-foreground">
              Ask about any Qatar Stock Exchange company in English or Arabic: price, performance, company details and
              website, results from the uploaded reports, or market news. Every answer cites its evidence, and numbers
              come only from the price source or the documents.
            </p>
            <div className="mx-auto inline-flex rounded-md border p-0.5 text-xs">
              {(["en", "ar"] as const).map((l) => (
                <button
                  key={l}
                  onClick={() => setLang(l)}
                  className={cn("rounded px-2 py-0.5", l === lang ? "bg-brand-primary text-white" : "text-muted-foreground")}
                >
                  {l === "en" ? "English" : "العربية"}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap justify-center gap-2" dir={lang === "ar" ? "rtl" : "ltr"}>
              {EXAMPLES[lang].map((ex) => (
                <button
                  key={ex}
                  onClick={() => send(ex)}
                  lang={lang}
                  className="rounded-full border bg-card px-3 py-1.5 text-sm text-brand-primary hover:bg-sidebar-accent"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div dir="auto" className="max-w-[75%] rounded-2xl rounded-se-sm bg-brand-primary px-4 py-2 text-sm text-white">
                {m.text}
              </div>
            </div>
          ) : m.role === "bot" ? (
            <div key={i} className="max-w-[85%]">
              <BotMessage reply={m.reply} msg={i} onAsk={(q) => void send(q)} />
            </div>
          ) : (
            <p key={i} className="text-sm text-loss">
              {m.text}
            </p>
          ),
        )}
        {busy && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Checking prices, company data and documents…
          </p>
        )}
        <div ref={end} />
      </div>
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send(text);
        }}
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(text);
            }
          }}
          rows={2}
          dir="auto"
          placeholder="e.g. What is Industries Qatar trading at?  /  كم سعر سهم صناعات قطر؟"
          className="min-h-12 flex-1 resize-none rounded-lg border bg-card px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button type="submit" disabled={busy || !text.trim()}>
          {busy ? <Loader2 className="animate-spin" /> : <Send />} Ask
        </Button>
      </form>
      <p className="text-xs text-muted-foreground">
        Not investment advice. Prices from Yahoo Finance via yfinance may be delayed; changes are calculated by the app.
      </p>
    </div>
  );
}
