import { ChangeArrow } from "../components/ChangeArrow";
import { CountUp } from "../components/CountUp";
import { DerivedTag, SceneFrame, useEnter } from "../components/SceneFrame";
import { alpha, useTheme } from "../theme/brand";
import type { KpiCard, SceneData } from "../types";

const Card: React.FC<{ card: KpiCard; index: number }> = ({ card, index }) => {
  const { c } = useTheme();
  const delay = 10 + index * 10;
  const enter = useEnter(delay);
  const color = card.tone === "loss" ? c.loss : card.tone === "gain" ? c.gain : c.primary;

  return (
    <div
      style={{
        flex: 1,
        background: "white",
        borderRadius: 32,
        padding: "48px 48px 44px",
        boxShadow: `0 20px 60px ${alpha(c.primary, 0.12)}`,
        borderTop: `10px solid ${color}`,
        display: "flex",
        flexDirection: "column",
        gap: 26,
        opacity: enter,
        transform: `translateY(${(1 - enter) * 60}px)`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <span style={{ fontSize: 38, fontWeight: 600, color: alpha(c.ink, 0.75) }}>{card.label}</span>
        {card.derived && <DerivedTag />}
      </div>
      <CountUp
        number={card.number}
        decimals={card.decimals}
        prefix={card.prefix}
        suffix={card.suffix}
        text={card.text}
        delay={delay + 6}
        style={{ fontSize: card.text.length > 16 ? 66 : 84, fontWeight: 800, color, lineHeight: 1.1 }}
      />
      <div style={{ marginTop: "auto", minHeight: 50 }}>{card.change && <ChangeArrow change={card.change} />}</div>
    </div>
  );
};

export const KpiCards: React.FC<{ data: SceneData }> = ({ data }) => (
  <SceneFrame title={data.title}>
    <div style={{ display: "flex", gap: 44, width: "100%", alignItems: "stretch", alignSelf: "center", height: 470 }}>
      {(data.cards ?? []).map((card, i) => (
        <Card key={card.key} card={card} index={i} />
      ))}
    </div>
  </SceneFrame>
);
