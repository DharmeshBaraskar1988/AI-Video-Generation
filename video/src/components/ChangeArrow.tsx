import { alpha, useTheme } from "../theme/brand";
import { localizeDigits } from "../theme/rtl";
import type { Change } from "../types";

/** Change chip: green up arrow / red down arrow, with what it is compared against. */
export const ChangeArrow: React.FC<{ change: Change; size?: number }> = ({ change, size = 30 }) => {
  const { c, digits } = useTheme();
  const color = change.direction === "up" ? c.gain : change.direction === "down" ? c.loss : c.ink;
  const rotate = change.direction === "up" ? 0 : change.direction === "down" ? 180 : 90;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size * 0.4, flexWrap: "wrap" }}>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: size * 0.25,
          padding: `${size * 0.15}px ${size * 0.45}px`,
          borderRadius: size,
          background: alpha(color, 0.12),
          color,
          fontWeight: 700,
          fontSize: size,
        }}
      >
        <svg width={size * 0.8} height={size * 0.8} viewBox="0 0 24 24" style={{ transform: `rotate(${rotate}deg)` }}>
          <path d="M12 3 L21 14 H15 V21 H9 V14 H3 Z" fill={color} />
        </svg>
        {localizeDigits(change.text, digits)}
      </span>
      <span style={{ fontSize: size * 0.7, color: alpha(c.ink, 0.6) }}>{change.basis}</span>
    </div>
  );
};
