import { DerivedTag, SceneFrame, useEnter } from "../components/SceneFrame";
import { alpha, useTheme } from "../theme/brand";
import { localizeDigits } from "../theme/rtl";
import type { SceneData, Stat } from "../types";

const StatCard: React.FC<{ stat: Stat; index: number; featured: boolean }> = ({ stat, index, featured }) => {
  const { c, digits } = useTheme();
  const enter = useEnter(10 + index * 12);
  return (
    <div
      style={{
        flex: 1,
        borderRadius: 30,
        padding: "46px 50px",
        background: featured ? c.primary : "white",
        color: featured ? "white" : c.ink,
        boxShadow: `0 18px 50px ${alpha(c.primary, 0.14)}`,
        display: "flex",
        flexDirection: "column",
        gap: 18,
        opacity: enter,
        transform: `scale(${0.92 + 0.08 * enter})`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 34, fontWeight: 600, opacity: 0.8 }}>{stat.label}</span>
        {stat.derived && <DerivedTag />}
      </div>
      {stat.when && (
        <span style={{ fontSize: 30, color: featured ? c.accent : alpha(c.ink, 0.6) }}>{localizeDigits(stat.when, digits)}</span>
      )}
      <span style={{ fontSize: 76, fontWeight: 800, marginTop: 10, fontVariantNumeric: "tabular-nums" }}>
        {localizeDigits(stat.text, digits)}
      </span>
    </div>
  );
};

export const Outlook: React.FC<{ data: SceneData }> = ({ data }) => (
  <SceneFrame title={data.title}>
    <div style={{ display: "flex", gap: 44, width: "100%", alignItems: "stretch", alignSelf: "center", height: 380 }}>
      {(data.stats ?? []).map((s, i) => (
        <StatCard key={i} stat={s} index={i} featured={i === 0} />
      ))}
    </div>
  </SceneFrame>
);
