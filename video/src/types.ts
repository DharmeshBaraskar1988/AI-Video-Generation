// Props contract (see CLAUDE.md "Video props"). Built by backend/app/services/props.py.

export type Direction = "ltr" | "rtl";

export type Brand = {
  name: string;
  tagline_en: string;
  tagline_ar: string;
  colors: {
    primary: string;
    accent: string;
    secondary: string;
    background: string;
    ink: string;
    gain: string;
    loss: string;
  };
};

export type Change = { text: string; direction: "up" | "down" | "flat"; basis: string };

export type KpiCard = {
  key: string;
  label: string;
  number: number;
  decimals: number;
  prefix: string;
  suffix: string;
  text: string; // exact final display, formatted in Python
  tone: "gain" | "loss" | "neutral";
  derived: boolean;
  change: Change | null;
};

export type Bar = {
  label: string;
  sublabel: string;
  value: number;
  text: string;
  derived: boolean;
  highlight: boolean;
};

export type Slice = { label: string; value: number; text: string };

export type Stat = { label: string; when: string | null; text: string; derived: boolean };

export type SceneData = {
  title?: string;
  // intro
  kicker?: string;
  company?: string;
  period?: string | null;
  // kpis
  cards?: KpiCard[];
  // trend
  bars?: Bar[];
  unit?: string;
  note?: string | null;
  // drivers
  items?: string[];
  // segments
  slices?: Slice[];
  // outlook
  stats?: Stat[];
  // outro
  tagline?: string;
  demoNote?: string | null;
  musicCredit?: string | null;
};

export type SceneType = "intro" | "kpis" | "trend" | "drivers" | "segments" | "outlook" | "outro";

export type Scene = {
  id: string;
  type: SceneType;
  start: number;
  end: number;
  audioStart: number;
  text: string;
  data: SceneData;
};

export type Word = { text: string; start: number; end: number };

export type PresenterStyle = { gender: "male" | "female" };

export type VideoProps = {
  language: "en" | "ar";
  direction: Direction;
  digits: "western" | "eastern";
  brand: Brand;
  audio: string;
  durationSeconds: number;
  scenes: Scene[];
  words: Word[];
  captions: boolean;
  demo: boolean;
  company: string;
  quarter: string;
  musicCredit?: string | null; // shown in the outro when the track's licence requires attribution
  presenter?: PresenterStyle | null; // animated presenter in the corner; null = off
};
