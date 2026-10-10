import { useMemo } from "react";
import { random, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { alpha, useTheme } from "../theme/brand";
import type { PresenterStyle, Word } from "../types";

// An original illustrated Gulf presenter (our own design), animated from the narration word timings:
// mouth opens per estimated syllable, eyes blink, the head sways while talking and the brows lift on figures.

export const PRESENTER_WIDTH = 400;
const VIEW_W = 400;
const VIEW_H = 520;

const syllables = (text: string): number => {
  const clean = text.replace(/[^\p{L}\p{N}]/gu, "");
  if (!clean) return 1;
  if (/\d/.test(clean)) return Math.max(1, Math.round(clean.replace(/\D/g, "").length * 1.4));
  if (/[؀-ۿ]/.test(clean)) return Math.max(1, Math.round(clean.length / 2.4));
  return Math.max(1, (clean.toLowerCase().match(/[aeiouy]+/g) ?? []).length);
};

/** 0 = closed, 1 = wide open, from which word is being spoken at time t. */
const mouthAt = (t: number, words: Word[], startIdx: number): number => {
  for (let i = startIdx; i < words.length; i++) {
    const w = words[i];
    if (w.start > t + 0.05) break;
    if (t > w.end + 0.05) continue;
    const len = Math.max(0.08, w.end - w.start);
    const p = Math.min(1, Math.max(0, (t - w.start) / len));
    // ramp in/out over 80 ms at the word edges (works for words shorter than the ramp)
    const env = Math.max(0, Math.min(1, (t - w.start + 0.05) / 0.08, (w.end + 0.05 - t) / 0.08));
    return env * (0.25 + 0.75 * Math.abs(Math.sin(p * syllables(w.text) * Math.PI)));
  }
  return 0;
};

/** One before the last word that starts at or before t (binary search; words are in time order). */
const wordIndex = (t: number, words: Word[]): number => {
  let lo = 0;
  let hi = words.length - 1;
  let ans = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (words[mid].start <= t) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return Math.max(0, ans - 1);
};

const BLINK_EVERY = 3.6;

const blinkAt = (t: number): number => {
  const k = Math.floor(t / BLINK_EVERY);
  const at = k * BLINK_EVERY + 0.4 + random(`blink-${k}`) * 2.4;
  const d = t - at;
  if (d < 0 || d > 0.18) return 1;
  return Math.abs(d - 0.09) / 0.09; // 1 -> 0 -> 1
};

export const Presenter: React.FC<{ words: Word[]; look: PresenterStyle }> = ({ words, look }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { c } = useTheme();
  const t = frame / fps;

  const idx = wordIndex(t, words);
  const open = mouthAt(t, words, idx);
  const near = words.slice(Math.max(0, idx - 1), idx + 3);
  const talking = near.some((w) => t >= w.start - 0.3 && t <= w.end + 0.4);
  const figure = near.some((w) => /\d/.test(w.text) && t >= w.start - 0.1 && t <= w.end + 0.3);

  const enter = spring({ frame, fps, config: { damping: 16 } });
  const sway = talking ? 1 : 0.35;
  const tilt = sway * (1.4 * Math.sin(t * 0.9) + 0.7 * Math.sin(t * 2.3 + 1));
  const nod = sway * 2.2 * Math.sin(t * 3.1);
  const breathe = 1 + 0.006 * Math.sin(t * 1.7);
  const brow = figure ? -5 : 0;
  const eyes = blinkAt(t);

  const female = look.gender === "female";
  const skin = female ? "#d9a985" : "#c48f66";
  const skinShade = female ? "#c08f6b" : "#a8734f";
  const cloth = female ? "#1d1f24" : "#f7f8fa"; // shayla / ghutra
  const clothShade = female ? "#0f1013" : "#dfe3e8";
  const robe = female ? "#22252b" : "#fbfcfd"; // abaya / kandura
  const robeShade = female ? "#121418" : "#dde2e7";
  const mouthH = female ? 6 : 8;

  const ids = useMemo(() => `p${Math.round(random(look.gender) * 1e6)}`, [look.gender]);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 0, // the robe runs under the caption band
        insetInlineEnd: 30,
        width: PRESENTER_WIDTH,
        height: (PRESENTER_WIDTH * VIEW_H) / VIEW_W,
        opacity: enter,
        transform: `translateY(${(1 - enter) * 80}px)`,
        pointerEvents: "none",
      }}
    >
      {/* soft glow so the figure reads on light and dark scenes */}
      <div
        style={{
          position: "absolute",
          left: "8%",
          right: "8%",
          top: "6%",
          bottom: "-4%",
          borderRadius: "50% 50% 0 0",
          background: `radial-gradient(circle at 50% 40%, ${alpha(c.accent, 0.35)}, ${alpha(c.accent, 0)} 70%)`,
        }}
      />
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} width="100%" height="100%" style={{ position: "absolute", inset: 0 }}>
        <defs>
          <linearGradient id={`${ids}-robe`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor={robeShade} />
            <stop offset="0.45" stopColor={robe} />
            <stop offset="1" stopColor={robeShade} />
          </linearGradient>
          <linearGradient id={`${ids}-cloth`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor={clothShade} />
            <stop offset="0.5" stopColor={cloth} />
            <stop offset="1" stopColor={clothShade} />
          </linearGradient>
          <radialGradient id={`${ids}-face`} cx="0.45" cy="0.4" r="0.7">
            <stop offset="0" stopColor={skin} />
            <stop offset="1" stopColor={skinShade} />
          </radialGradient>
        </defs>

        <g transform={`translate(200 520) scale(1 ${breathe}) translate(-200 -520)`}>
          {/* cloth falling behind the shoulders */}
          <path d="M112 150 C100 250 88 330 58 420 L342 420 C312 330 300 250 288 150 Z" fill={clothShade} />
          {/* robe */}
          <path d="M24 520 C26 410 70 336 150 314 L250 314 C330 336 374 410 376 520 Z" fill={`url(#${ids}-robe)`} />
          {female ? (
            <path d="M200 330 L200 520" stroke={alpha("#ffffff", 0.08)} strokeWidth={3} />
          ) : (
            <>
              {/* kandura collar and tassel (tarboosha) */}
              <path d="M176 312 Q200 334 224 312" stroke="#c9ced5" strokeWidth={4} fill="none" />
              <path d="M200 326 L200 396" stroke="#c9ced5" strokeWidth={3} />
              <ellipse cx={200} cy={404} rx={5} ry={10} fill="#c9ced5" />
            </>
          )}
          {/* neck */}
          <path d="M170 250 L170 312 Q200 330 230 312 L230 250 Z" fill={skinShade} />
        </g>

        {/* head group: sways and nods */}
        <g transform={`rotate(${tilt} 200 300) translate(0 ${nod * 0.4})`}>
          {/* face */}
          <ellipse cx={200} cy={192} rx={62} ry={80} fill={`url(#${ids}-face)`} />
          {!female && (
            <>
              {/* trimmed beard */}
              <path
                d="M139 190 C138 258 168 288 200 288 C232 288 262 258 261 190 C256 226 238 244 200 246 C162 244 144 226 139 190 Z"
                fill="#2a1f1a"
              />
              {/* moustache */}
              <path d="M178 225 Q200 214 222 225 Q212 231 200 228 Q188 231 178 225 Z" fill="#2a1f1a" />
            </>
          )}
          {/* nose */}
          <path d="M200 184 Q195 204 192 210 Q200 215 208 210" stroke={skinShade} strokeWidth={3} fill="none" strokeLinecap="round" />
          {/* mouth */}
          <g transform={`translate(200 ${female ? 236 : 238})`}>
            <ellipse cx={0} cy={0} rx={13 + open * 2} ry={1.8 + open * mouthH} fill="#5b2626" />
            {open > 0.35 && <rect x={-9} y={-1.8 - open * mouthH} width={18} height={open * 3.5} rx={2} fill="#f3eee9" />}
            {female && <ellipse cx={0} cy={0} rx={15 + open * 2} ry={3.6 + open * mouthH} fill="none" stroke="#b5615a" strokeWidth={3.2} />}
          </g>
          {/* eyes */}
          {[176, 224].map((x) => (
            <g key={x} transform={`translate(${x} 180) scale(1 ${Math.max(0.08, eyes)})`}>
              <ellipse cx={0} cy={0} rx={11} ry={7.5} fill="#fbf8f4" />
              <circle cx={0} cy={0.5} r={5.5} fill="#3b2618" />
              <circle cx={1.6} cy={-1.4} r={1.6} fill="#ffffff" />
              {female && <path d="M-12 -4 Q0 -11 12 -4" stroke="#1b1412" strokeWidth={2.4} fill="none" />}
            </g>
          ))}
          {/* brows lift on figures */}
          <g transform={`translate(0 ${brow})`}>
            <path d="M160 163 Q176 155 190 162" stroke="#2a1f1a" strokeWidth={female ? 3.5 : 5.5} fill="none" strokeLinecap="round" />
            <path d="M210 162 Q224 155 240 163" stroke="#2a1f1a" strokeWidth={female ? 3.5 : 5.5} fill="none" strokeLinecap="round" />
          </g>

          {/* head cloth: cap over the forehead plus side panels framing the face */}
          <path
            d="M116 222 C108 128 148 86 200 86 C252 86 292 128 284 222 L266 222 C266 162 244 136 200 136 C156 136 134 162 134 222 Z"
            fill={`url(#${ids}-cloth)`}
          />
          <path d="M116 214 C110 290 98 350 80 420 L140 428 C144 350 142 286 136 214 Z" fill={`url(#${ids}-cloth)`} />
          <path d="M284 214 C290 290 302 350 320 420 L260 428 C256 350 258 286 264 214 Z" fill={`url(#${ids}-cloth)`} />
          {/* fold lines */}
          <path d="M126 240 C122 300 114 350 102 410" stroke={clothShade} strokeWidth={3} fill="none" />
          <path d="M274 240 C278 300 286 350 298 410" stroke={clothShade} strokeWidth={3} fill="none" />
          {!female && (
            <>
              {/* agal (black cord ring) */}
              <path d="M122 124 Q200 150 278 124" stroke="#151515" strokeWidth={9} fill="none" strokeLinecap="round" />
              <path d="M126 110 Q200 136 274 110" stroke="#151515" strokeWidth={8} fill="none" strokeLinecap="round" />
            </>
          )}
        </g>
      </svg>
    </div>
  );
};
