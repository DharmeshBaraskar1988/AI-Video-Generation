import { interpolate, useCurrentFrame } from "remotion";
import { SceneFrame } from "../components/SceneFrame";
import { alpha, useTheme } from "../theme/brand";
import { inReadingOrder, localizeDigits } from "../theme/rtl";
import type { SceneData } from "../types";

const FULL_W = 1700;
const NARROW_W = 1360; // leaves room for the presenter
const H = 560;
const LABEL_SPACE = 110; // under the chart for quarter labels
const VALUE_SPACE = 56; // above/below bars for value text

/** Net profit by quarter. Losses drop below the zero line in the loss colour. */
export const TrendChart: React.FC<{ data: SceneData }> = ({ data }) => {
  const { c, dir, digits, presenter } = useTheme();
  const W = presenter ? NARROW_W : FULL_W;
  const frame = useCurrentFrame();
  const bars = inReadingOrder(data.bars ?? [], dir);

  const max = Math.max(...bars.map((b) => Math.max(0, b.value)), 1);
  const min = Math.min(...bars.map((b) => Math.min(0, b.value)), 0);
  const plotH = H - LABEL_SPACE - VALUE_SPACE * (min < 0 ? 2 : 1);
  const scale = plotH / (max - min);
  const zeroY = VALUE_SPACE + max * scale;
  const slot = W / bars.length;
  const barW = Math.min(150, slot * 0.55);

  return (
    <SceneFrame title={data.title} subtitle={data.unit}>
      <div style={{ display: "flex", flexDirection: "column", width: "100%", alignItems: "center" }}>
        <svg width={W} height={H} style={{ overflow: "visible" }}>
          <defs>
            <pattern id="hatch" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="14" height="14" fill="transparent" />
              <line x1="0" y1="0" x2="0" y2="14" stroke="white" strokeWidth="5" strokeOpacity="0.35" />
            </pattern>
          </defs>
          {bars.map((b, i) => {
            const grow = interpolate(frame, [10 + i * 6, 40 + i * 6], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            });
            const h = Math.abs(b.value) * scale * grow;
            const x = i * slot + (slot - barW) / 2;
            const negative = b.value < 0;
            const y = negative ? zeroY : zeroY - h;
            const color = negative ? c.loss : b.highlight ? c.accent : c.primary;
            const textY = negative ? zeroY + h + 44 : zeroY - h - 18;
            return (
              <g key={i}>
                <rect x={x} y={y} width={barW} height={h} rx={10} fill={color} opacity={b.highlight || negative ? 1 : 0.85} />
                {b.derived && <rect x={x} y={y} width={barW} height={h} rx={10} fill="url(#hatch)" />}
                {b.highlight && (
                  <rect x={x - 8} y={y - 8} width={barW + 16} height={h + 16} rx={14} fill="none" stroke={c.accent} strokeWidth={4} />
                )}
                <text
                  x={x + barW / 2}
                  y={textY}
                  textAnchor="middle"
                  fontSize={34}
                  fontWeight={700}
                  fill={negative ? c.loss : c.ink}
                  opacity={grow}
                >
                  {localizeDigits(b.text, digits)}
                </text>
                <text x={x + barW / 2} y={H - LABEL_SPACE + 46 + (min < 0 ? 0 : 0)} textAnchor="middle" fontSize={32} fontWeight={600} fill={c.ink}>
                  {b.label}
                </text>
                <text x={x + barW / 2} y={H - LABEL_SPACE + 86} textAnchor="middle" fontSize={28} fill={alpha(c.ink, 0.6)}>
                  {localizeDigits(b.sublabel, digits)}
                </text>
              </g>
            );
          })}
          {/* zero line */}
          <line x1={0} x2={W} y1={zeroY} y2={zeroY} stroke={c.ink} strokeWidth={3} />
        </svg>
        {data.note && (
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 10, fontSize: 26, color: alpha(c.ink, 0.65) }}>
            <svg width={34} height={22}>
              <rect width={34} height={22} rx={4} fill={c.primary} opacity={0.85} />
              <rect width={34} height={22} rx={4} fill="url(#hatch)" />
            </svg>
            {data.note}
          </div>
        )}
      </div>
    </SceneFrame>
  );
};
