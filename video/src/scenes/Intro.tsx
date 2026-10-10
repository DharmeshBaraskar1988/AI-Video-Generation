import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Logo } from "../components/Logo";
import { useEnter } from "../components/SceneFrame";
import { alpha, useTheme } from "../theme/brand";
import { localizeDigits } from "../theme/rtl";
import type { SceneData } from "../types";

const BARS = [0.35, 0.55, 0.45, 0.75, 0.6, 0.95];

export const Intro: React.FC<{ data: SceneData }> = ({ data }) => {
  const { c, dir, digits, presenter } = useTheme();
  const frame = useCurrentFrame();
  const logo = useEnter(0, 14);
  const kicker = useEnter(10);
  const name = useEnter(16);
  const period = useEnter(24);

  return (
    <AbsoluteFill dir={dir} style={{ background: c.primary, color: "white", overflow: "hidden" }}>
      {/* rising bars motif (the presenter stands there when shown) */}
      <div
        style={{
          position: "absolute",
          insetInlineEnd: 120,
          bottom: 150,
          display: presenter ? "none" : "flex",
          alignItems: "flex-end",
          gap: 26,
          height: 520,
        }}
      >
        {BARS.map((h, i) => {
          const grow = interpolate(frame, [8 + i * 5, 38 + i * 5], [0, h], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <div
              key={i}
              style={{
                width: 70,
                height: `${grow * 100}%`,
                borderRadius: "14px 14px 0 0",
                background: i === BARS.length - 1 ? c.accent : alpha("#ffffff", 0.1 + i * 0.03),
              }}
            />
          );
        })}
      </div>

      <div style={{ position: "absolute", top: 150, insetInlineStart: 140, display: "flex", flexDirection: "column", gap: 34 }}>
        <div style={{ transform: `scale(${0.8 + 0.2 * logo})`, opacity: logo, transformOrigin: dir === "rtl" ? "right" : "left" }}>
          <Logo height={120} />
        </div>
        <div
          style={{
            marginTop: 70,
            fontSize: 38,
            fontWeight: 600,
            letterSpacing: dir === "rtl" ? 0 : 6,
            textTransform: "uppercase",
            color: c.accent,
            opacity: kicker,
            transform: `translateY(${(1 - kicker) * 20}px)`,
          }}
        >
          {data.kicker}
        </div>
        <div
          style={{
            fontSize: 128,
            fontWeight: 800,
            lineHeight: 1.05,
            maxWidth: 1100,
            opacity: name,
            transform: `translateY(${(1 - name) * 30}px)`,
          }}
        >
          {data.company}
        </div>
        <div style={{ fontSize: 72, fontWeight: 600, color: alpha("#ffffff", 0.85), opacity: period }}>
          {localizeDigits(data.period ?? "", digits)}
        </div>
      </div>
    </AbsoluteFill>
  );
};
