"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Clock, Loader2, Send, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
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

type Reply = {
  question: string;
  lang: "en" | "ar";
  ok: boolean;
  answer: string;
  source_line: string;
  answer_by: "llm" | "template" | "fallback";
  model: string | null;
  companies: { symbol: string; name_en: string; name_ar: string }[];
  quotes: Quote[];
  histories: History[];
};

type Message = { role: "user"; text: string } | { role: "bot"; reply: Reply } | { role: "error"; text: string };

const EXAMPLES = {
  en: [
    "What is Industries Qatar trading at?",
    "Compare QNB and Ooredoo over the last 3 months",
    "How has Qatar Islamic Bank performed this year?",
    "Why did Industries Qatar fall this week?",
  ],
  ar: ["كم سعر سهم صناعات قطر؟", "ما أداء بنك قطر الوطني خلال الشهر الماضي؟", "قارن بين أريدُ وفودافون قطر", "لماذا انخفض سهم صناعات قطر هذا الأسبوع؟"],
};

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

function BotMessage({ reply }: { reply: Reply }) {
  const rtl = reply.lang === "ar";
  const q0 = reply.quotes[0];
  return (
    <div className="space-y-2">
      <div
        dir={rtl ? "rtl" : "ltr"}
        lang={reply.lang}
        className={cn(
          "rounded-2xl rounded-ss-sm border bg-card px-4 py-3 text-sm leading-6 shadow-sm",
          !reply.ok && "border-brand-accent/60 bg-brand-accent/10",
        )}
      >
        {!reply.ok && <TriangleAlert className="me-1 inline size-4 text-brand-secondary" />}
        {reply.answer}
        {reply.source_line && <p className="mt-2 text-xs text-muted-foreground">{reply.source_line}</p>}
      </div>
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
  const end = useRef<HTMLDivElement>(null);

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
      const reply = await api<Reply>("/api/stock/chat", { method: "POST", body: JSON.stringify({ question }) });
      setMessages((m) => [...m, { role: "bot", reply }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: (e as Error).message }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col gap-4">
      <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border bg-background/50 p-4">
        {messages.length === 0 && (
          <div className="space-y-3 py-6 text-center">
            <p className="text-sm text-muted-foreground">
              Ask about any Qatar Stock Exchange company, in English or Arabic. Prices come from the price source with the
              time they were valid; the assistant never guesses a number.
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
              <BotMessage reply={m.reply} />
            </div>
          ) : (
            <p key={i} className="text-sm text-loss">
              {m.text}
            </p>
          ),
        )}
        {busy && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Fetching prices…
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
