"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Film, Loader2, Mic, Music, Save, ShieldCheck, Upload } from "lucide-react";
import { VoicePicker, type Voice } from "@/components/VoicePicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, API_URL } from "@/lib/api";
import type { QuartersResponse } from "@/lib/quarters";
import { formatSeconds } from "@/lib/scripts";
import { cn } from "@/lib/utils";

type Values = {
  voice_engine: "edge" | "silma";
  voice_en: string;
  voice_ar: string;
  voice_rate: string;
  voice_rate_en: string;
  voice_rate_ar: string;
  music_track: string;
  music_volume: number;
  target_seconds: number;
  languages: ("en" | "ar")[];
  captions: boolean;
  social_cut: boolean;
  require_review: boolean;
  enforce_length: boolean;
  require_audio_review: boolean;
  llm_model: string;
  arabic_digits: "western" | "eastern";
  presenter: "auto" | "male" | "female" | "off";
};
type Track = { file: string; credit: string | null; size_kb: number };
type CustomVoice = { id: string; name: string; speaker: string; language: string; created_at: string };
type SettingsResponse = { values: Values; music_tracks: Track[]; custom_voices: CustomVoice[] };
type Models = { models: string[]; fallbacks: string[]; exhausted: Record<string, number> };

const CONSENT =
  "I confirm that the person whose voice is in this recording has given explicit consent for it to be used to create a synthetic voice for D-Storify videos, and that the recording is not copied from YouTube or anyone else's recordings.";

async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data as T;
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-start gap-3 py-1">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 size-4 accent-[var(--brand-primary)]" />
      <span>
        <span className="text-sm font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </span>
    </label>
  );
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

const selectCls = "h-9 w-full rounded-md border bg-background px-2 text-sm";

export default function AdminPage() {
  const [data, setData] = useState<SettingsResponse | null>(null);
  const [values, setValues] = useState<Values | null>(null);
  const [voices, setVoices] = useState<{ en: Voice[]; ar: Voice[] } | null>(null);
  const [models, setModels] = useState<Models | null>(null);
  const [quarters, setQuarters] = useState<{ company: string; period: string; id: string; label: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api<SettingsResponse>("/api/settings").then((d) => {
      setData(d);
      setValues(d.values);
    });
    api<{ en: Voice[]; ar: Voice[] }>("/api/settings/voices").then(setVoices).catch(() => setVoices({ en: [], ar: [] }));
    api<Models>("/api/settings/models").then(setModels).catch(() => undefined);
    api<QuartersResponse>("/api/quarters").then((q) =>
      setQuarters(
        q.companies.flatMap((c) =>
          c.quarters.map((p) => ({ company: c.id, period: p.id, id: p.video_id, label: `${c.company.ticker} · ${p.period}` })),
        ),
      ),
    );
  }, []);

  const dirty = useMemo(() => JSON.stringify(values) !== JSON.stringify(data?.values), [values, data]);
  const set = <K extends keyof Values>(key: K, v: Values[K]) => setValues((prev) => (prev ? { ...prev, [key]: v } : prev));

  const save = async () => {
    if (!values || !data) return;
    const changed = Object.fromEntries(
      Object.entries(values).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(data.values[k as keyof Values])),
    );
    setSaving(true);
    setMessage(null);
    try {
      const r = await api<{ values: Values }>("/api/settings", { method: "PUT", body: JSON.stringify(changed) });
      setData({ ...data, values: r.values });
      setValues(r.values);
      setMessage({ ok: true, text: "Saved. The next script, narration or render uses these settings." });
    } catch (e) {
      setMessage({ ok: false, text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  if (!values || !data) return <p className="text-sm text-muted-foreground">Loading settings…</p>;

  return (
    <div className="space-y-6">
      <header className="sticky top-0 z-10 -mx-2 flex flex-wrap items-center gap-3 rounded-lg bg-background/95 px-2 py-2 backdrop-blur">
        <h1 className="text-2xl font-semibold text-brand-primary">Admin</h1>
        {dirty && <Badge variant="outline">Unsaved changes</Badge>}
        <Button className="ms-auto" onClick={save} disabled={!dirty || saving}>
          {saving ? <Loader2 className="animate-spin" /> : <Save />} Save settings
        </Button>
      </header>
      {message && (
        <p className={cn("rounded-md border p-2 text-sm", message.ok ? "border-gain/40 bg-gain/5 text-gain" : "border-loss/40 bg-loss/5 text-loss")}>
          {message.text}
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Mic className="size-5 text-brand-primary" /> Voices
            </CardTitle>
            <CardDescription>Free Microsoft neural voices (edge-tts). Changes apply to the next narration.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="Voice engine">
              <select value={values.voice_engine} onChange={(e) => set("voice_engine", e.target.value as Values["voice_engine"])} className={selectCls}>
                <option value="edge">Edge TTS (free neural voices)</option>
                <option value="silma" disabled>
                  SILMA custom voice (not installed in this POC)
                </option>
              </select>
            </Field>
            {(["en", "ar"] as const).map((lang) => (
              <VoicePicker
                key={lang}
                lang={lang}
                voices={voices?.[lang] ?? []}
                voice={values[`voice_${lang}`]}
                rate={values[`voice_rate_${lang}`]}
                onChange={(voice, rate) => setValues((p) => (p ? { ...p, [`voice_${lang}`]: voice, [`voice_rate_${lang}`]: rate } : p))}
              />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Film className="size-5 text-brand-primary" /> Video
            </CardTitle>
            <CardDescription>Length, languages and extras for new videos.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label={`Target length: ${formatSeconds(values.target_seconds)}`} hint="The script writer aims for this length. English aims at about 2 minutes so the longer Arabic lands near 3. Turn on &quot;Enforce 2-3 minute video length&quot; below to make it a hard limit.">
              <input
                type="range"
                min={120}
                max={180}
                step={15}
                value={values.target_seconds}
                onChange={(e) => set("target_seconds", Number(e.target.value))}
                className="w-full accent-[var(--brand-primary)]"
              />
            </Field>
            <div>
              <span className="text-sm font-medium">Languages</span>
              <div className="flex gap-4">
                {(["en", "ar"] as const).map((l) => (
                  <Toggle
                    key={l}
                    label={l === "en" ? "English" : "Arabic"}
                    checked={values.languages.includes(l)}
                    onChange={(on) => {
                      const next = on ? [...new Set([...values.languages, l])] : values.languages.filter((x) => x !== l);
                      if (next.length) set("languages", next as Values["languages"]);
                    }}
                  />
                ))}
              </div>
            </div>
            <Toggle label="Captions" hint="Word-by-word captions burned into the video" checked={values.captions} onChange={(v) => set("captions", v)} />
            <div>
              <span className="text-sm font-medium">Presenter</span>
              <span className="block text-xs text-muted-foreground">Animated character who speaks the narration, beside the charts</span>
              <div className="flex flex-wrap gap-4">
                {([["auto", "Match the voice"], ["male", "Male"], ["female", "Female"], ["off", "Off"]] as const).map(([v, label]) => (
                  <label key={v} className="flex items-center gap-2 py-1 text-sm">
                    <input type="radio" checked={values.presenter === v} onChange={() => set("presenter", v)} className="accent-[var(--brand-primary)]" />
                    {label}
                  </label>
                ))}
              </div>
            </div>
            <Toggle label="15-second social cut" hint="Intro + headline figures, for social media" checked={values.social_cut} onChange={(v) => set("social_cut", v)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Music className="size-5 text-brand-primary" /> Music
            </CardTitle>
            <CardDescription>Royalty-free background track, mixed under the voice and ducked while it speaks. Changes apply to the next narration (use Re-record in the audio review).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="Track">
              <select value={values.music_track} onChange={(e) => set("music_track", e.target.value)} className={selectCls}>
                {data.music_tracks.map((t) => (
                  <option key={t.file} value={t.file}>
                    {t.file}
                  </option>
                ))}
              </select>
            </Field>
            <audio src={`${API_URL}/files/music/${values.music_track}`} controls className="h-8 w-full" />
            {data.music_tracks.find((t) => t.file === values.music_track)?.credit && (
              <p className="text-xs text-muted-foreground">{data.music_tracks.find((t) => t.file === values.music_track)?.credit}</p>
            )}
            <Field label={`Music volume: ${Math.round(values.music_volume * 100)}%`}>
              <input
                type="range"
                min={0}
                max={0.4}
                step={0.01}
                value={values.music_volume}
                onChange={(e) => set("music_volume", Number(e.target.value))}
                className="w-full accent-[var(--brand-primary)]"
              />
            </Field>
            <MusicUpload onUploaded={(tracks) => setData({ ...data, music_tracks: tracks })} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldCheck className="size-5 text-brand-primary" /> Review, model and digits
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Toggle
              label="Require human review before rendering"
              hint="When off, a script that passes every number and length check is approved automatically."
              checked={values.require_review}
              onChange={(v) => set("require_review", v)}
            />
            <Toggle
              label="Review audio before creating the video"
              hint="After narration, pause so you can listen to each language with its music, then approve (or re-record with new voice/music settings) before the video is rendered."
              checked={values.require_audio_review}
              onChange={(v) => set("require_audio_review", v)}
            />
            <Toggle
              label="Enforce 2-3 minute video length"
              hint="When on, scripts outside 2-3 minutes cannot be approved and long narrations are sped up or blocked. When off, the length is only a target for the script writer."
              checked={values.enforce_length}
              onChange={(v) => set("enforce_length", v)}
            />
            <Field
              label="Language model"
              hint={
                models
                  ? `If its free daily quota runs out, these are used next: ${models.fallbacks.join(", ")}.` +
                    (Object.keys(models.exhausted).length
                      ? ` Used up today: ${Object.entries(models.exhausted).map(([m, h]) => `${m} (resets in ${h} h)`).join(", ")}.`
                      : "")
                  : undefined
              }
            >
              <select value={values.llm_model} onChange={(e) => set("llm_model", e.target.value)} className={selectCls}>
                {!models?.models.includes(values.llm_model) && <option value={values.llm_model}>{values.llm_model}</option>}
                {models?.models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </Field>
            <div>
              <span className="text-sm font-medium">Digits in Arabic videos</span>
              <div className="flex gap-4">
                {(["western", "eastern"] as const).map((d) => (
                  <label key={d} className="flex items-center gap-2 py-1 text-sm">
                    <input type="radio" checked={values.arabic_digits === d} onChange={() => set("arabic_digits", d)} className="accent-[var(--brand-primary)]" />
                    {d === "western" ? "Western (1.7)" : "Arabic-Indic (١٫٧)"}
                  </label>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        <CustomVoiceCard initial={data.custom_voices} />
        <NotebookLMCard quarters={quarters} />
      </div>
    </div>
  );
}

function MusicUpload({ onUploaded }: { onUploaded: (tracks: Track[]) => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (!open)
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Upload /> Add a track
      </Button>
    );
  return (
    <form
      className="space-y-2 rounded-lg border p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setMsg(null);
        try {
          const r = await upload<{ file: string; music_tracks: Track[] }>("/api/settings/music", new FormData(e.currentTarget));
          onUploaded(r.music_tracks);
          setMsg({ ok: true, text: `Added ${r.file}. Select it above and save.` });
          e.currentTarget.reset();
        } catch (err) {
          setMsg({ ok: false, text: (err as Error).message });
        } finally {
          setBusy(false);
        }
      }}
    >
      <Input name="file" type="file" accept=".mp3,audio/mpeg" required />
      <Input name="title" placeholder="Title and artist" required />
      <Input name="licence" placeholder="Licence, e.g. CC BY 4.0 or Pixabay Content License" required />
      <Input name="source_url" placeholder="Source URL" />
      <Input name="credit" placeholder="Credit line, if the licence requires one" />
      <Button type="submit" size="sm" disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <Upload />} Upload MP3
      </Button>
      {msg && <p className={cn("text-xs", msg.ok ? "text-gain" : "text-loss")}>{msg.text}</p>}
    </form>
  );
}

function CustomVoiceCard({ initial }: { initial: CustomVoice[] }) {
  const [list, setList] = useState(initial);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Mic className="size-5 text-brand-secondary" /> Custom voice <Badge variant="outline">stretch</Badge>
        </CardTitle>
        <CardDescription>
          Reference clip for a cloned voice (SILMA engine, not installed in this POC). Only with the speaker&apos;s consent;
          voices copied from YouTube or other people&apos;s recordings are not allowed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          className="space-y-2"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setMsg(null);
            const form = new FormData(e.currentTarget);
            form.set("consent", consent ? "true" : "false");
            try {
              const r = await upload<{ custom_voices: CustomVoice[]; note: string }>("/api/settings/custom-voices", form);
              setList(r.custom_voices);
              setMsg({ ok: true, text: r.note });
              e.currentTarget.reset();
              setConsent(false);
            } catch (err) {
              setMsg({ ok: false, text: (err as Error).message });
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="grid grid-cols-2 gap-2">
            <Input name="name" placeholder="Voice name" required />
            <Input name="speaker" placeholder="Speaker's full name" required />
          </div>
          <select name="language" className={selectCls} defaultValue="ar">
            <option value="ar">Arabic</option>
            <option value="en">English</option>
          </select>
          <Input name="clip" type="file" accept=".wav,.mp3,.m4a" required />
          <label className="flex items-start gap-2 rounded-md border border-brand-secondary/30 bg-brand-secondary/5 p-2 text-xs">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 accent-[var(--brand-secondary)]" />
            <span>{CONSENT}</span>
          </label>
          <Button type="submit" size="sm" variant="outline" disabled={busy || !consent}>
            {busy ? <Loader2 className="animate-spin" /> : <Upload />} Save reference clip
          </Button>
          {msg && <p className={cn("text-xs", msg.ok ? "text-gain" : "text-loss")}>{msg.text}</p>}
        </form>
        {list.length > 0 && (
          <ul className="space-y-1 text-sm">
            {list.map((v) => (
              <li key={v.id} className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-gain" /> {v.name} · {v.speaker} · {v.language.toUpperCase()}
                <span className="text-xs text-muted-foreground">consent recorded {new Date(v.created_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function NotebookLMCard({ quarters }: { quarters: { company: string; period: string; id: string; label: string }[] }) {
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string; videoId?: string } | null>(null);
  const chosen = quarters.find((q) => q.id === target) ?? quarters[0];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Upload className="size-5 text-brand-primary" /> Import NotebookLM video
        </CardTitle>
        <CardDescription>
          NotebookLM has no API: make the video there, download the MP4 and attach it to a quarter. It appears as an
          alternative on that quarter&apos;s video page.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!chosen) return;
            setBusy(true);
            setMsg(null);
            try {
              const r = await upload<{ video_id: string }>(
                `/api/quarters/${chosen.company}/${chosen.period}/notebooklm`,
                new FormData(e.currentTarget),
              );
              setMsg({ ok: true, text: "Imported.", videoId: r.video_id });
              e.currentTarget.reset();
            } catch (err) {
              setMsg({ ok: false, text: (err as Error).message });
            } finally {
              setBusy(false);
            }
          }}
        >
          <select value={chosen?.id ?? ""} onChange={(e) => setTarget(e.target.value)} className={selectCls}>
            {quarters.map((q) => (
              <option key={q.id} value={q.id}>
                {q.label}
              </option>
            ))}
          </select>
          <Input name="file" type="file" accept=".mp4,video/mp4" required />
          <Button type="submit" size="sm" disabled={busy || !chosen}>
            {busy ? <Loader2 className="animate-spin" /> : <Upload />} Import MP4
          </Button>
          {msg && (
            <p className={cn("text-xs", msg.ok ? "text-gain" : "text-loss")}>
              {msg.text}{" "}
              {msg.videoId && (
                <Link href={`/videos/${msg.videoId}`} className="underline">
                  Open video page
                </Link>
              )}
            </p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
