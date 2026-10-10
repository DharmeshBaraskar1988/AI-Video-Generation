import { SceneFrame, useEnter } from "../components/SceneFrame";
import { alpha, useTheme } from "../theme/brand";
import { localizeDigits } from "../theme/rtl";
import type { SceneData } from "../types";

const Item: React.FC<{ text: string; index: number }> = ({ text, index }) => {
  const { c, dir, digits } = useTheme();
  const enter = useEnter(10 + index * 12);
  return (
    <div
      style={{
        display: "flex",
        gap: 30,
        alignItems: "flex-start",
        background: "white",
        borderRadius: 26,
        padding: "34px 40px",
        boxShadow: `0 14px 40px ${alpha(c.primary, 0.1)}`,
        opacity: enter,
        transform: `translateX(${(1 - enter) * (dir === "rtl" ? -60 : 60)}px)`,
      }}
    >
      <div
        style={{
          flexShrink: 0,
          width: 64,
          height: 64,
          borderRadius: 18,
          background: c.primary,
          color: c.accent,
          fontSize: 34,
          fontWeight: 800,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {localizeDigits(String(index + 1), digits)}
      </div>
      <div
        style={{
          fontSize: 36,
          lineHeight: 1.35,
          fontWeight: 500,
          display: "-webkit-box",
          WebkitLineClamp: 3,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {localizeDigits(text, digits)}
      </div>
    </div>
  );
};

export const Drivers: React.FC<{ data: SceneData }> = ({ data }) => (
  <SceneFrame title={data.title}>
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 34,
        width: "100%",
        alignContent: "center",
      }}
    >
      {(data.items ?? []).slice(0, 4).map((text, i) => (
        <Item key={i} text={text} index={i} />
      ))}
    </div>
  </SceneFrame>
);
