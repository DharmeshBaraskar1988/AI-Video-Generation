"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Save,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { ChipEditor, type ChipEditorHandle } from "@/components/ChipEditor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import {
  formatSeconds,
  type Checks,
  type Placeholder,
  type Scene,
  type Script,
} from "@/lib/scripts";
import { cn } from "@/lib/utils";

const PLACEHOLDER_RE = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;
// Measured speed of the default voices (keep in sync with backend factcheck.WPM).
const WPM = { en: 131, ar: 104 } as const;
const SCENE_PAUSE = 0.6;
const MIN_SECONDS = 120; // every video (EN and AR) runs 2-3 minutes
const MAX_SECONDS = 180;
const SCENE_TYPES = [
  "intro",
  "kpis",
  "trend",
  "drivers",
  "segments",
  "outlook",
  "outro",
] as const;

function estimate(wordCount: number, lang: "en" | "ar"): number {
  return (wordCount / WPM[lang]) * 60;
}

function fill(
  text: string,
  placeholders: Record<string, Placeholder>,
  lang: "en" | "ar",
): string {
  return text.replace(PLACEHOLDER_RE, (m, key: string) => {
    const p = placeholders[key];
    return p ? (lang === "ar" ? p.display_ar : p.display_en) : m;
  });
}

function words(text: string): number {
  const t = text.trim();
  return t ? t.split(/\s+/).length : 0;
}

function editsOf(scenes: Scene[]) {
  return scenes.map(({ id, en, ar, type }) => ({ id, en, ar, type }));
}

function sceneIssues(checks: Checks | null, sceneId: string) {
  if (!checks) return [];
  return [
    ...checks.stray_numbers
      .filter((s) => s.scene === sceneId)
      .map((s) => ({
        lang: s.lang,
        text: `Number typed by hand: "${s.text}". Use "Insert figure" instead.`,
      })),
    ...checks.unknown_placeholders
      .filter((u) => u.scene === sceneId)
      .map((u) => ({ lang: u.lang, text: `Unknown placeholder {{${u.key}}}` })),
    ...checks.placeholder_mismatch
      .filter((m) => m.scene === sceneId)
      .map((m) => ({
        lang: "ar",
        text: `Arabic must use the same figures as English. EN: ${m.en.join(", ") || "none"} · AR: ${m.ar.join(", ") || "none"}`,
      })),
  ];
}

function LengthBar({
  en,
  ar,
  target,
}: {
  en: number;
  ar: number;
  target: number;
}) {
  const longest = Math.max(en, ar, target);
  const max = Math.max(longest * 1.1, MAX_SECONDS * 1.15);
  const pct = (v: number) => `${Math.min(100, (v / max) * 100)}%`;
  const tone = (v: number) =>
    v < MIN_SECONDS || v > MAX_SECONDS ? "bg-loss" : "bg-gain";
  return (
    <div className="min-w-64 flex-1 space-y-1">
      <div className="flex flex-wrap justify-between gap-x-3 text-xs text-muted-foreground">
        <span>
          EN about{" "}
          <strong className="text-brand-ink">{formatSeconds(en)}</strong> · AR
          about <strong className="text-brand-ink">{formatSeconds(ar)}</strong>
        </span>
        <span>
          {formatSeconds(MIN_SECONDS)}–{formatSeconds(MAX_SECONDS)} · target{" "}
          {formatSeconds(target)}
        </span>
      </div>
      <div className="relative space-y-0.5">
        <div className="h-1.5 rounded-full bg-muted">
          <div
            className={cn("h-1.5 rounded-full transition-all", tone(en))}
            style={{ width: pct(en) }}
          />
        </div>
        <div className="h-1.5 rounded-full bg-muted">
          <div
            className={cn(
              "h-1.5 rounded-full opacity-70 transition-all",
              tone(ar),
            )}
            style={{ width: pct(ar) }}
          />
        </div>
        <div
          title="2-minute minimum"
          className="absolute -top-1 h-5 w-0.5 bg-loss"
          style={{ insetInlineStart: pct(MIN_SECONDS) }}
        />
        <div
          title="3-minute maximum"
          className="absolute -top-1 h-5 w-0.5 bg-loss"
          style={{ insetInlineStart: pct(MAX_SECONDS) }}
        />
        <div
          title="target"
          className="absolute -top-1 h-5 w-0.5 bg-brand-ink"
          style={{ insetInlineStart: pct(target) }}
        />
      </div>
    </div>
  );
}

function FigurePicker({
  placeholders,
  lang,
  onPick,
}: {
  placeholders: Record<string, Placeholder>;
  lang: "en" | "ar";
  onPick: (key: string) => void;
}) {
  return (
    <select
      value=""
      onChange={(e) => e.target.value && onPick(e.target.value)}
      className="h-7 w-40 min-w-0 truncate rounded-md border bg-background px-2 text-xs text-muted-foreground"
      aria-label="Insert figure"
    >
      <option value="">+ Insert figure…</option>
      {Object.entries(placeholders).map(([key, p]) => (
        <option key={key} value={key}>
          {(lang === "ar" ? p.display_ar : p.display_en) +
            " · " +
            p.label +
            (p.derived ? " (derived)" : "")}
        </option>
      ))}
    </select>
  );
}

function SceneCard({
  scene,
  index,
  total,
  placeholders,
  issues,
  regenerating,
  onChange,
  onMove,
  onRegenerate,
  onDelete,
  onAddBelow,
}: {
  scene: Scene;
  index: number;
  total: number;
  placeholders: Record<string, Placeholder>;
  issues: { lang: string; text: string }[];
  regenerating: boolean;
  onChange: (lang: "en" | "ar", text: string) => void;
  onMove: (delta: number) => void;
  onRegenerate: (instruction: string) => void;
  onDelete: () => void;
  onAddBelow: (type: string) => void;
}) {
  const enRef = useRef<ChipEditorHandle>(null);
  const arRef = useRef<ChipEditorHandle>(null);
  const [instruction, setInstruction] = useState("");
  const wEn = words(fill(scene.en, placeholders, "en"));
  const wAr = words(fill(scene.ar, placeholders, "ar"));
  const empty = !scene.en.trim() || !scene.ar.trim();

  return (
    <Card className={cn(issues.length > 0 && "ring-2 ring-loss/50")}>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <span className="font-semibold">Scene {index + 1}</span>
        <Badge variant="outline" className="capitalize">
          {scene.type}
        </Badge>
        {scene.visual?.chart && (
          <Badge variant="outline">{scene.visual.chart}</Badge>
        )}
        <span className="text-xs text-muted-foreground">
          EN {wEn} words · {formatSeconds(estimate(wEn, "en"))} · AR{" "}
          {formatSeconds(estimate(wAr, "ar"))}
        </span>
        <div className="ms-auto flex items-center gap-1">
          <Button
            size="icon-sm"
            variant="ghost"
            disabled={index === 0}
            onClick={() => onMove(-1)}
            aria-label="Move up"
          >
            <ArrowUp />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            disabled={index === total - 1}
            onClick={() => onMove(1)}
            aria-label="Move down"
          >
            <ArrowDown />
          </Button>
          <select
            value=""
            onChange={(e) => e.target.value && onAddBelow(e.target.value)}
            className="h-7 rounded-md border bg-background px-1.5 text-xs text-muted-foreground"
            aria-label="Add a scene below"
            title="Add a scene below this one"
          >
            <option value="">+ Scene below…</option>
            {SCENE_TYPES.map((t) => (
              <option key={t} value={t} className="capitalize">
                {t}
              </option>
            ))}
          </select>
          <Button
            size="icon-sm"
            variant="ghost"
            className="text-loss hover:text-loss"
            disabled={total <= 1}
            onClick={onDelete}
            aria-label="Delete scene"
            title="Delete scene"
          >
            <Trash2 />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
              <span className="shrink-0">English</span>
              <FigurePicker
                placeholders={placeholders}
                lang="en"
                onPick={(k) => enRef.current?.insertPlaceholder(k)}
              />
            </div>
            <ChipEditor
              ref={enRef}
              value={scene.en}
              lang="en"
              placeholders={placeholders}
              onChange={(t) => onChange("en", t)}
            />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
              <span className="shrink-0">
                <bdi lang="ar">العربية</bdi> · {wAr} words
              </span>
              <FigurePicker
                placeholders={placeholders}
                lang="ar"
                onPick={(k) => arRef.current?.insertPlaceholder(k)}
              />
            </div>
            <ChipEditor
              ref={arRef}
              value={scene.ar}
              lang="ar"
              placeholders={placeholders}
              onChange={(t) => onChange("ar", t)}
            />
          </div>
        </div>

        {empty && (
          <p className="rounded-md border border-dashed p-2 text-xs text-muted-foreground">
            This scene needs text in English and Arabic. Type it, or press{" "}
            <strong>Regenerate scene</strong> (add an instruction such as
            &ldquo;cover the dividend&rdquo;) to have it written in both
            languages.
          </p>
        )}

        {issues.length > 0 && (
          <ul className="space-y-0.5 rounded-md border border-loss/40 bg-loss/5 p-2 text-xs text-loss">
            {issues.map((issue, i) => (
              <li key={i}>
                <strong>{issue.lang.toUpperCase()}:</strong> {issue.text}
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="Optional instruction, e.g. shorter, mention the steel restart"
            className="h-8 max-w-md flex-1 text-xs"
            onKeyDown={(e) =>
              e.key === "Enter" && !regenerating && onRegenerate(instruction)
            }
          />
          <Button
            size="sm"
            variant="outline"
            disabled={regenerating}
            onClick={() => onRegenerate(instruction)}
          >
            {regenerating ? (
              <Loader2 className="animate-spin" />
            ) : (
              <RefreshCw />
            )}
            Regenerate scene
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function ScriptEditor({
  initial,
  onApproved,
}: {
  initial: Script;
  onApproved: () => void;
}) {
  const videoId = initial.video_id;
  const placeholders = initial.placeholders;
  const [scenes, setScenes] = useState<Scene[]>(initial.scenes);
  const [saved, setSaved] = useState(() =>
    JSON.stringify(editsOf(initial.scenes)),
  );
  const [status, setStatus] = useState(initial.status);
  const [savedChecks, setSavedChecks] = useState<Checks>(initial.checks);
  const [liveChecks, setLiveChecks] = useState<Checks | null>(null);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState<"save" | "approve" | null>(null);
  const [regenerating, setRegenerating] = useState<string | null>(null);
  const [message, setMessage] = useState<{
    tone: "ok" | "error";
    text: string;
  } | null>(null);

  const dirty = JSON.stringify(editsOf(scenes)) !== saved;
  // Unchanged text shows the saved result; edited text shows the latest live check.
  const checks = dirty ? (liveChecks ?? savedChecks) : savedChecks;

  // Live fact check (server-side, no LLM) shortly after typing stops.
  useEffect(() => {
    if (!dirty) return;
    setChecking(true);
    const t = setTimeout(() => {
      api<Checks>(`/api/scripts/${videoId}/check`, {
        method: "POST",
        body: JSON.stringify({ scenes: editsOf(scenes) }),
      })
        .then(setLiveChecks)
        .catch(() => undefined)
        .finally(() => setChecking(false));
    }, 500);
    return () => clearTimeout(t);
  }, [scenes, dirty, videoId]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const [secondsEn, secondsAr] = useMemo(() => {
    const pauses = SCENE_PAUSE * Math.max(0, scenes.length - 1);
    const total = (lang: "en" | "ar") =>
      estimate(
        scenes.reduce(
          (n, s) => n + words(fill(s[lang], placeholders, lang)),
          0,
        ),
        lang,
      ) + pauses;
    return [total("en"), total("ar")];
  }, [scenes, placeholders]);
  const tooShort = Math.min(secondsEn, secondsAr) < MIN_SECONDS;
  const tooLong = Math.max(secondsEn, secondsAr) > MAX_SECONDS;
  // The 2-3 minute range only blocks approval when the admin switch "Enforce length" is on.
  const enforceLength = savedChecks?.enforce_length ?? false;
  const lengthBlocks = enforceLength && (tooShort || tooLong);
  const hasEmpty = scenes.some((s) => !s.en.trim() || !s.ar.trim());

  const update = (id: string, lang: "en" | "ar", text: string) =>
    setScenes((prev) =>
      prev.map((s) => (s.id === id ? { ...s, [lang]: text } : s)),
    );

  const move = (index: number, delta: number) =>
    setScenes((prev) => {
      const next = [...prev];
      const [item] = next.splice(index, 1);
      next.splice(index + delta, 0, item);
      return next;
    });

  const remove = (id: string) => {
    const scene = scenes.find((s) => s.id === id);
    if (
      scene &&
      (scene.en.trim() || scene.ar.trim()) &&
      !window.confirm(`Delete this ${scene.type} scene?`)
    )
      return;
    setScenes((prev) => prev.filter((s) => s.id !== id));
  };

  const addBelow = (index: number, type: string) =>
    setScenes((prev) => {
      const used = new Set(prev.map((s) => s.id));
      let n = prev.length + 1;
      while (used.has(`s${n}`)) n++;
      const scene: Scene = {
        id: `s${n}`,
        type,
        en: "",
        ar: "",
        data_keys: [],
        visual: { chart: null, series: [], highlight: null },
      };
      const next = [...prev];
      next.splice(index + 1, 0, scene);
      return next;
    });

  const save = useCallback(async (): Promise<Script | null> => {
    setBusy("save");
    setMessage(null);
    try {
      const res = await api<Script>(`/api/scripts/${videoId}`, {
        method: "PUT",
        body: JSON.stringify({ scenes: editsOf(scenes) }),
      });
      setSaved(JSON.stringify(editsOf(res.scenes)));
      setSavedChecks(res.checks);
      setLiveChecks(null);
      setStatus(res.status);
      setMessage(
        res.checks.passed
          ? { tone: "ok", text: "Saved. All numbers match the data file." }
          : {
              tone: "error",
              text: "Saved, but some numbers need fixing before you can approve.",
            },
      );
      return res;
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
      return null;
    } finally {
      setBusy(null);
    }
  }, [scenes, videoId]);

  const approve = async () => {
    if (dirty) {
      const res = await save();
      if (!res?.checks.passed) return;
    }
    setBusy("approve");
    try {
      await api(`/api/scripts/${videoId}/approve`, { method: "POST" });
      setStatus("approved");
      setMessage({
        tone: "ok",
        text: "Approved. Narration and rendering follow in the next steps.",
      });
      onApproved();
    } catch (e) {
      setMessage({ tone: "error", text: (e as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const regenerate = async (sceneId: string, instruction: string) => {
    setRegenerating(sceneId);
    setMessage(null);
    try {
      const res = await api<{ scene: Scene }>(
        `/api/scripts/${videoId}/scenes/${sceneId}/regenerate`,
        {
          method: "POST",
          body: JSON.stringify({ instruction, scenes: editsOf(scenes) }),
        },
      );
      setScenes((prev) =>
        prev.map((s) =>
          s.id === sceneId ? { ...s, en: res.scene.en, ar: res.scene.ar } : s,
        ),
      );
    } catch (e) {
      setMessage({
        tone: "error",
        text: `Regenerate failed: ${(e as Error).message}`,
      });
    } finally {
      setRegenerating(null);
    }
  };

  const passed = checks?.passed ?? false;

  return (
    <div className="space-y-4">
      <div className="sticky top-0 z-10 -mx-2 flex flex-wrap items-center gap-4 rounded-lg border bg-card/95 p-3 shadow-sm backdrop-blur">
        <LengthBar
          en={secondsEn}
          ar={secondsAr}
          target={initial.target_seconds}
        />
        <div className="flex items-center gap-1.5 text-sm">
          {checking && dirty ? (
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          ) : passed ? (
            <ShieldCheck className="size-4 text-gain" />
          ) : (
            <ShieldAlert className="size-4 text-loss" />
          )}
          <span className={passed ? "text-gain" : "text-loss"}>
            {checks
              ? `${checks.numbers_ok}/${checks.numbers_total} numbers verified`
              : "Not checked"}
          </span>
        </div>
        <Badge
          variant="outline"
          className={cn(status === "approved" && "border-gain text-gain")}
        >
          {status === "approved"
            ? "Approved"
            : dirty
              ? "Unsaved changes"
              : "Draft"}
        </Badge>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={save}
            disabled={!dirty || busy !== null}
          >
            {busy === "save" ? <Loader2 className="animate-spin" /> : <Save />}
            Save
          </Button>
          <Button
            onClick={approve}
            disabled={
              busy !== null ||
              !passed ||
              lengthBlocks ||
              hasEmpty ||
              (status === "approved" && !dirty)
            }
            title={
              !passed
                ? "Fix the flagged numbers first"
                : hasEmpty
                  ? "Every scene needs English and Arabic text"
                  : lengthBlocks
                    ? "Videos must run 2 to 3 minutes"
                    : undefined
            }
          >
            {busy === "approve" ? (
              <Loader2 className="animate-spin" />
            ) : (
              <CheckCircle2 />
            )}
            Approve
          </Button>
        </div>
      </div>

      {(tooShort || tooLong) && (
        <p
          className={cn(
            "rounded-md border p-2 text-sm",
            enforceLength
              ? "border-loss/40 bg-loss/5 text-loss"
              : "border-amber-500/40 bg-amber-500/5 text-amber-700 dark:text-amber-400",
          )}
        >
          This script would run {tooShort ? "under 2" : "over 3"} minutes (EN{" "}
          {formatSeconds(secondsEn)}, AR {formatSeconds(secondsAr)}).{" "}
          {enforceLength
            ? tooShort
              ? "Add content before approving."
              : "Shorten it before approving: edit the text, regenerate a scene with the instruction “shorter”, or delete a scene. Arabic runs about a quarter longer than English."
            : "The length limit is off in Admin settings, so you can still approve it."}
        </p>
      )}

      {message && (
        <p
          className={cn(
            "rounded-md border p-2 text-sm",
            message.tone === "ok"
              ? "border-gain/40 bg-gain/5 text-gain"
              : "border-loss/40 bg-loss/5 text-loss",
          )}
        >
          {message.text}
        </p>
      )}

      {scenes.map((scene, i) => (
        <SceneCard
          key={scene.id}
          scene={scene}
          index={i}
          total={scenes.length}
          placeholders={placeholders}
          issues={sceneIssues(checks, scene.id)}
          regenerating={regenerating === scene.id}
          onChange={(lang, text) => update(scene.id, lang, text)}
          onMove={(d) => move(i, d)}
          onRegenerate={(instr) => regenerate(scene.id, instr)}
          onDelete={() => remove(scene.id)}
          onAddBelow={(type) => addBelow(i, type)}
        />
      ))}
    </div>
  );
}
