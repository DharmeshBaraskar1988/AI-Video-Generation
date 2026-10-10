"use client";

import { useRef, useState } from "react";
import { AlertTriangle, FileText, Loader2, PlayCircle, Send, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, API_URL } from "@/lib/api";
import { formatSeconds } from "@/lib/scripts";
import { cn } from "@/lib/utils";

type Lang = "en" | "ar";

export type QATimestamp = { seconds: number; lang: Lang; scene: string; scene_type: string };

type Citation =
  | { kind: "script"; scene: string; scene_type: string; lang: Lang; start: number; text: string }
  | { kind: "document"; file: string; page: number; section: string; text: string };

type Answer = {
  question: string;
  lang: Lang;
  covered: boolean;
  answer: string;
  citations: Citation[];
  timestamp: QATimestamp | null;
  unverified: string[];
  model: string | null;
};

const SUGGESTED: Record<Lang, string[]> = {
  en: [
    "Why was there a loss in Q2?",
    "How did revenue change?",
    "Which segment performed best?",
    "How strong is the balance sheet?",
  ],
  ar: ["لماذا سجّلت الشركة خسارة في الربع الثاني؟", "كيف تغيّرت الإيرادات؟", "ما القطاع الأفضل أداءً؟", "ما مدى قوة المركز المالي؟"],
};

const UI = {
  en: { placeholder: "Ask about this video…", explained: "Explained at", listen: "Listen", source: "Source" },
  ar: { placeholder: "اسأل عن هذا الفيديو…", explained: "الشرح عند", listen: "استمع", source: "المصدر" },
};

function AnswerCard({ a, onJump }: { a: Answer; onJump: (t: QATimestamp) => void }) {
  const [audio, setAudio] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  const rtl = a.lang === "ar";
  const t = UI[a.lang];

  const listen = async () => {
    setSpeaking(true);
    try {
      const r = await api<{ audio: string }>("/api/qa/speak", { method: "POST", body: JSON.stringify({ text: a.answer, lang: a.lang }) });
      setAudio(`${API_URL}/outputs/${r.audio}`);
    } finally {
      setSpeaking(false);
    }
  };

  return (
    <div className="space-y-2 rounded-lg border bg-background/60 p-3">
      <p className="text-sm font-medium" dir={rtl ? "rtl" : "ltr"} lang={a.lang}>
        {a.question}
      </p>
      <p
        className={cn("text-sm leading-6", !a.covered && "text-muted-foreground italic")}
        dir={rtl ? "rtl" : "ltr"}
        lang={a.lang}
      >
        {a.answer}
      </p>
      {a.unverified.length > 0 && (
        <p className="flex items-center gap-1 text-xs text-loss">
          <AlertTriangle className="size-3.5" /> Not found in the cited sources: {a.unverified.join(", ")}
        </p>
      )}
      {a.covered && (
        <div className="flex flex-wrap items-center gap-1.5">
          {a.timestamp && (
            <Button size="sm" onClick={() => onJump(a.timestamp!)}>
              <PlayCircle /> {t.explained} {formatSeconds(a.timestamp.seconds)}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={listen} disabled={speaking}>
            {speaking ? <Loader2 className="animate-spin" /> : <Volume2 />} {t.listen}
          </Button>
        </div>
      )}
      {audio && <audio src={audio} controls autoPlay className="h-8 w-full" />}
      {a.citations.length > 0 && (
        <div className="space-y-1">
          <div className="flex flex-wrap gap-1">
            {a.citations.map((c, i) => (
              <button
                key={i}
                onClick={() => setOpen(open === i ? null : i)}
                className={cn(
                  "inline-flex items-center gap-1 rounded border px-1.5 text-[11px] leading-5",
                  open === i ? "border-brand-primary bg-brand-primary text-white" : "border-brand-primary/30 text-brand-primary",
                )}
              >
                {c.kind === "script" ? (
                  <>
                    <PlayCircle className="size-3" /> video · {c.scene_type}
                  </>
                ) : (
                  <>
                    <FileText className="size-3" /> {c.file.replace(/\.pdf$/, "")} p.{c.page}
                  </>
                )}
              </button>
            ))}
          </div>
          {open !== null && (
            <pre
              className="max-h-48 overflow-auto rounded border bg-card p-2 font-sans text-[11px] leading-5 whitespace-pre-wrap"
              dir={a.citations[open].kind === "script" && a.citations[open].lang === "ar" ? "rtl" : "ltr"}
            >
              {a.citations[open].text}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/** Ask questions beside the player; answers cite the script / documents and can jump the video. */
export function QAPanel({
  videoId,
  watchLang,
  onJump,
}: {
  videoId: string;
  watchLang: Lang;
  onJump: (t: QATimestamp) => void;
}) {
  const [lang, setLang] = useState<Lang>("en");
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  const ask = async (q: string) => {
    const text = q.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const a = await api<Answer>("/api/qa", {
        method: "POST",
        body: JSON.stringify({ video_id: videoId, question: text, watch_lang: watchLang }),
      });
      setAnswers((prev) => [a, ...prev]);
      setQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const rtl = lang === "ar";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2">
        <CardTitle className="text-base">Ask about this video</CardTitle>
        <div className="ms-auto inline-flex rounded-md border p-0.5 text-xs">
          {(["en", "ar"] as Lang[]).map((l) => (
            <button
              key={l}
              onClick={() => setLang(l)}
              className={cn("rounded px-2 py-0.5", l === lang ? "bg-brand-primary text-white" : "text-muted-foreground")}
            >
              {l === "en" ? "EN" : "عربي"}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1.5" dir={rtl ? "rtl" : "ltr"}>
          {SUGGESTED[lang].map((s) => (
            <button
              key={s}
              onClick={() => ask(s)}
              disabled={busy}
              lang={lang}
              className="rounded-full border px-2.5 py-1 text-xs text-brand-primary hover:bg-sidebar-accent disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void ask(question);
          }}
        >
          <textarea
            ref={input}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask(question);
              }
            }}
            rows={2}
            dir={rtl ? "rtl" : "auto"}
            lang={lang}
            placeholder={UI[lang].placeholder}
            className="min-h-10 flex-1 resize-none rounded-md border bg-background px-2 py-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button type="submit" size="icon" disabled={busy || !question.trim()} aria-label="Ask">
            {busy ? <Loader2 className="animate-spin" /> : <Send />}
          </Button>
        </form>
        {busy && <p className="text-xs text-muted-foreground">Searching the video and documents…</p>}
        {error && <p className="text-xs text-loss">{error}</p>}
        <div className="max-h-[60vh] space-y-2 overflow-y-auto">
          {answers.map((a, i) => (
            <AnswerCard key={answers.length - i} a={a} onJump={onJump} />
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">
          Answers come only from this video&apos;s script and the results PDFs. Questions outside them are declined.
        </p>
      </CardContent>
    </Card>
  );
}
