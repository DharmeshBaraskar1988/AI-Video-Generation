import { interpolate, useCurrentFrame } from "remotion";
import { SceneFrame, useEnter } from "../components/SceneFrame";
import { alpha, useTheme } from "../theme/brand";
import { localizeDigits } from "../theme/rtl";
import type { SceneData } from "../types";

const R = 210;
const STROKE = 96;
const CIRC = 2 * Math.PI * R;

/** Revenue share donut that sweeps in, with a legend. */
export const Segments: React.FC<{ data: SceneData }> = ({ data }) => {
  const { c, digits } = useTheme();
  const frame = useCurrentFrame();
  const slices = data.slices ?? [];
  const total = slices.reduce((n, s) => n + s.value, 0) || 1;
  const colors = [c.primary, c.accent, c.secondary, c.gain, c.loss];
  const sweep = interpolate(frame, [8, 50], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  let offset = 0;
  return (
    <SceneFrame title={data.title} subtitle={data.period}>
      <div style={{ display: "flex", alignItems: "center", gap: 120, width: "100%", justifyContent: "center" }}>
        <svg width={(R + STROKE) * 2} height={(R + STROKE) * 2} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={R + STROKE} cy={R + STROKE} r={R} fill="none" stroke={alpha(c.ink, 0.06)} strokeWidth={STROKE} />
          {slices.map((s, i) => {
            const len = (s.value / total) * CIRC;
            const shown = Math.max(0, Math.min(len, sweep * CIRC - offset));
            const el = (
              <circle
                key={i}
                cx={R + STROKE}
                cy={R + STROKE}
                r={R}
                fill="none"
                stroke={colors[i % colors.length]}
                strokeWidth={STROKE}
                strokeDasharray={`${Math.max(0, shown - 4)} ${CIRC}`}
                strokeDashoffset={-offset}
              />
            );
            offset += len;
            return el;
          })}
        </svg>
        <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
          {slices.map((s, i) => (
            <LegendRow key={i} index={i} color={colors[i % colors.length]} label={s.label} text={localizeDigits(s.text, digits)} />
          ))}
        </div>
      </div>
    </SceneFrame>
  );
};

const LegendRow: React.FC<{ index: number; color: string; label: string; text: string }> = ({ index, color, label, text }) => {
  const { c } = useTheme();
  const enter = useEnter(20 + index * 10);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 28, opacity: enter }}>
      <div style={{ width: 44, height: 44, borderRadius: 12, background: color }} />
      <div style={{ fontSize: 44, fontWeight: 600, minWidth: 380 }}>{label}</div>
      <div style={{ fontSize: 56, fontWeight: 800, color: c.primary, fontVariantNumeric: "tabular-nums" }}>{text}</div>
    </div>
  );
};
