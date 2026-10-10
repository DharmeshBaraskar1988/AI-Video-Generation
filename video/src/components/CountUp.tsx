import { Easing, interpolate, useCurrentFrame } from "remotion";
import { useTheme } from "../theme/brand";
import { localizeDigits } from "../theme/rtl";

/**
 * Counts from 0 to `number`, then shows `text` exactly (the Python-formatted value), so the
 * final frame always matches the verified display string.
 */
export const CountUp: React.FC<{
  number: number;
  decimals: number;
  prefix: string;
  suffix: string;
  text: string;
  delay?: number;
  duration?: number;
  style?: React.CSSProperties;
}> = ({ number, decimals, prefix, suffix, text, delay = 0, duration = 40, style }) => {
  const frame = useCurrentFrame();
  const { digits } = useTheme();
  const p = interpolate(frame - delay, [0, duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const shown =
    p >= 1
      ? text
      : `${prefix}${(number * p).toLocaleString("en-US", {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })}${suffix}`;
  return <span style={{ fontVariantNumeric: "tabular-nums", ...style }}>{localizeDigits(shown, digits)}</span>;
};
