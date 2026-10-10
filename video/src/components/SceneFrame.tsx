import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { alpha, useTheme } from "../theme/brand";
import { Logo } from "./Logo";
import { PRESENTER_WIDTH } from "./Presenter";

/** Spring from 0 to 1 starting at `delay` frames. */
export const useEnter = (delay = 0, damping = 18): number => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping } });
};

export const CAPTION_SPACE = 170;

/** Shared layout for content scenes: title with accent bar, small logo, room for captions. */
export const SceneFrame: React.FC<{ title?: string; subtitle?: string | null; children: React.ReactNode }> = ({
  title,
  subtitle,
  children,
}) => {
  const { c, dir, presenter } = useTheme();
  const enter = useEnter(0);
  const frame = useCurrentFrame();
  const bar = interpolate(frame, [4, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill dir={dir} style={{ background: c.background, color: c.ink }}>
      {/* corner shape */}
      <div
        style={{
          position: "absolute",
          insetInlineEnd: -220,
          top: -260,
          width: 760,
          height: 760,
          borderRadius: "50%",
          background: alpha(c.primary, 0.06),
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 70,
          insetInlineStart: 110,
          insetInlineEnd: 110,
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
        }}
      >
        <div style={{ opacity: enter, transform: `translateY(${(1 - enter) * 30}px)` }}>
          <div style={{ fontSize: 64, fontWeight: 700, color: c.primary, lineHeight: 1.15 }}>{title}</div>
          <div style={{ height: 8, width: 160 * bar, background: c.accent, borderRadius: 4, marginTop: 18 }} />
          {subtitle && <div style={{ fontSize: 30, marginTop: 18, color: alpha(c.ink, 0.6) }}>{subtitle}</div>}
        </div>
        <div style={{ opacity: 0.9 }}>
          <Logo height={56} card={false} />
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          top: subtitle ? 290 : 250,
          bottom: CAPTION_SPACE + 40,
          insetInlineStart: presenter ? 90 : 110,
          insetInlineEnd: presenter ? PRESENTER_WIDTH + 50 : 110,
          display: "flex",
        }}
      >
        {children}
      </div>
    </AbsoluteFill>
  );
};

/** Small "derived" tag for calculated (not reported) figures. */
export const DerivedTag: React.FC<{ size?: number }> = ({ size = 22 }) => {
  const { c, lang } = useTheme();
  return (
    <span
      style={{
        fontSize: size,
        padding: `${size * 0.1}px ${size * 0.5}px`,
        border: `2px dashed ${c.accent}`,
        borderRadius: size,
        color: alpha(c.ink, 0.75),
        fontStyle: lang === "ar" ? "normal" : "italic",
      }}
    >
      {lang === "ar" ? "محسوب" : "derived"}
    </span>
  );
};
