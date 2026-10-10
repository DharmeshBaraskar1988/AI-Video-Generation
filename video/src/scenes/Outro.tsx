import { AbsoluteFill } from "remotion";
import { Logo } from "../components/Logo";
import { useEnter } from "../components/SceneFrame";
import { alpha, useTheme } from "../theme/brand";
import type { SceneData } from "../types";

export const Outro: React.FC<{ data: SceneData }> = ({ data }) => {
  const { c, dir } = useTheme();
  const logo = useEnter(0, 14);
  const text = useEnter(12);
  return (
    <AbsoluteFill
      dir={dir}
      style={{
        background: c.primary,
        color: "white",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: 50,
        paddingBottom: 170,
      }}
    >
      <div style={{ transform: `scale(${0.85 + 0.15 * logo})`, opacity: logo }}>
        <Logo height={150} />
      </div>
      <div style={{ fontSize: 72, fontWeight: 700, opacity: text }}>{data.company}</div>
      <div style={{ fontSize: 40, color: c.accent, opacity: text }}>{data.tagline}</div>
      {data.demoNote && (
        <div
          style={{
            marginTop: 30,
            fontSize: 28,
            padding: "14px 30px",
            borderRadius: 40,
            border: `2px solid ${alpha("#ffffff", 0.35)}`,
            color: alpha("#ffffff", 0.85),
            opacity: text,
          }}
        >
          {data.demoNote}
        </div>
      )}
      {data.musicCredit && (
        <div style={{ position: "absolute", bottom: 180, fontSize: 20, color: alpha("#ffffff", 0.55), opacity: text }}>
          {data.musicCredit}
        </div>
      )}
    </AbsoluteFill>
  );
};
