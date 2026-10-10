import { useMemo } from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { alpha, useTheme } from "../theme/brand";
import { localizeDigits } from "../theme/rtl";
import type { Word } from "../types";

type Line = { words: Word[]; start: number; end: number };

const MAX_WORDS = 9;
const MAX_CHARS = 52; // keeps each caption to one line at 46px
const BREAK_AFTER = /[.!?؟؛;:,،]$/;

/** Group words into short caption lines: break at punctuation, long pauses or the word limit. */
const toLines = (words: Word[]): Line[] => {
  const lines: Line[] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    const prev = words[i - 1];
    const pause = prev ? w.start - prev.end : 0;
    const chars = cur.reduce((n, x) => n + x.text.length + 1, 0) + w.text.length;
    if (
      cur.length &&
      (cur.length >= MAX_WORDS || chars > MAX_CHARS || pause > 0.45 || (BREAK_AFTER.test(prev.text) && cur.length >= 4))
    ) {
      lines.push({ words: cur, start: cur[0].start, end: cur[cur.length - 1].end });
      cur = [];
    }
    cur.push(w);
  });
  if (cur.length) lines.push({ words: cur, start: cur[0].start, end: cur[cur.length - 1].end });
  return lines;
};

/** Bottom caption band; the word being spoken is highlighted. */
export const Captions: React.FC<{ words: Word[] }> = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { c, dir, digits } = useTheme();
  const t = frame / fps;
  const lines = useMemo(() => toLines(words), [words]);

  const idx = lines.findIndex((l, i) => t >= l.start - 0.15 && t < (lines[i + 1]?.start ?? l.end + 0.6) - 0.15);
  const line = lines[idx];
  if (!line || t > line.end + 0.6) return null;

  const opacity = interpolate(t, [line.start - 0.15, line.start], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <div
      style={{
        position: "absolute",
        insetInline: 0,
        bottom: 0,
        height: 150,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: `linear-gradient(to top, ${alpha(c.primary, 0.96)}, ${alpha(c.primary, 0.85)})`,
        padding: "0 120px",
      }}
    >
      <div dir={dir} style={{ opacity, fontSize: 46, lineHeight: 1.3, textAlign: "center", color: "white", fontWeight: 500 }}>
        {line.words.map((w, i) => {
          // one highlighted word at a time: a word stays active until the next one starts
          const next = line.words[i + 1];
          const active = t >= w.start && (next ? t < next.start : t < w.end + 0.05);
          const spoken = t >= w.start;
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                margin: "0 7px",
                padding: "0 8px",
                borderRadius: 8,
                background: active ? c.accent : "transparent",
                color: active ? c.ink : "white",
                opacity: spoken ? 1 : 0.55,
              }}
            >
              {localizeDigits(w.text, digits)}
            </span>
          );
        })}
      </div>
    </div>
  );
};
