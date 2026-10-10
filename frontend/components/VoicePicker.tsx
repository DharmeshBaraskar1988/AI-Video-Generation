"use client";

import { useState } from "react";
import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, API_URL } from "@/lib/api";

export type Voice = { name: string; locale: string; gender: string; label: string };

const rateToNumber = (rate: string) => Number.parseInt(rate.replace("%", ""), 10) || 0;
const numberToRate = (n: number) => `${n >= 0 ? "+" : ""}${n}%`;

/** Voice + speed for one language, with a preview of a sample sentence. */
export function VoicePicker({
  lang,
  voices,
  voice,
  rate,
  onChange,
}: {
  lang: "en" | "ar";
  voices: Voice[];
  voice: string;
  rate: string;
  onChange: (voice: string, rate: string) => void;
}) {
  const [audio, setAudio] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locales = [...new Set(voices.map((v) => v.locale))];

  const preview = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ audio: string }>("/api/settings/voices/preview", {
        method: "POST",
        body: JSON.stringify({ voice, lang, rate }),
      });
      setAudio(`${API_URL}/outputs/${r.audio}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex items-center justify-between">
        <span className="font-medium">{lang === "en" ? "English voice" : "Arabic voice · الصوت العربي"}</span>
        <Button size="sm" variant="outline" onClick={preview} disabled={busy || !voice}>
          {busy ? <Loader2 className="animate-spin" /> : <Play />} Preview
        </Button>
      </div>
      <select
        value={voice}
        onChange={(e) => {
          setAudio(null);
          onChange(e.target.value, rate);
        }}
        className="h-9 w-full rounded-md border bg-background px-2 text-sm"
      >
        {!voices.some((v) => v.name === voice) && <option value={voice}>{voice}</option>}
        {locales.map((loc) => (
          <optgroup key={loc} label={loc}>
            {voices
              .filter((v) => v.locale === loc)
              .map((v) => (
                <option key={v.name} value={v.name}>
                  {v.label}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
      <label className="flex items-center gap-3 text-sm">
        <span className="w-14 text-muted-foreground">Speed</span>
        <input
          type="range"
          min={-30}
          max={30}
          step={5}
          value={rateToNumber(rate)}
          onChange={(e) => {
            setAudio(null);
            onChange(voice, numberToRate(Number(e.target.value)));
          }}
          className="flex-1 accent-[var(--brand-primary)]"
        />
        <span className="tabular w-12 text-end">{rate}</span>
      </label>
      {audio && <audio src={audio} controls autoPlay className="h-8 w-full" />}
      {error && <p className="text-xs text-loss">{error}</p>}
    </div>
  );
}
