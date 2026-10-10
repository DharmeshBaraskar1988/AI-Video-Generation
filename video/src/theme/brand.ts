import { createContext, useContext } from "react";
import brandJson from "../../../data/brand/brand.json";
import type { Brand, VideoProps } from "../types";

// data/brand/brand.json is the default; props.brand (from the back end) overrides it.
export const defaultBrand: Brand = brandJson as Brand;

export type Theme = {
  brand: Brand;
  c: Brand["colors"];
  lang: VideoProps["language"];
  dir: VideoProps["direction"];
  digits: VideoProps["digits"];
  font: string;
};

export const ThemeContext = createContext<Theme | null>(null);

export const useTheme = (): Theme => {
  const t = useContext(ThemeContext);
  if (!t) throw new Error("ThemeContext missing");
  return t;
};

/** Hex colour with alpha, e.g. alpha("#0F3D3E", 0.2). */
export const alpha = (hex: string, a: number): string => {
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};
