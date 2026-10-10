export type SummaryItem = {
  en: string;
  ar?: string;
  citations: string[]; // keys into Summary.sources (K1, K2, ...)
  verified: boolean;
  unverified: { en?: string[]; ar?: string[] };
  label?: string;
};

export type Source = {
  id: string;
  file: string;
  path?: string; // stored file name (uploaded documents)
  page: number;
  section: string;
  type: "text" | "table";
  text: string;
};

export type Summary = {
  title_en: string;
  title_ar: string;
  executive: SummaryItem[];
  sections: { id: string; title_en: string; title_ar: string; points: SummaryItem[] }[];
  sources: Record<string, Source>;
  documents: { file: string; pages: number }[];
  checks: { bullets: number; verified: number; uncited: number };
  model: string;
  generated_at: string;
};

export type SummaryState = { status: "idle" | "running" | "done" | "failed"; error: string | null; started_at: string | null };

export type DocumentInfo = {
  file: string;
  size_kb: number;
  indexed: boolean;
  pages: number | null;
  chunks: number | null;
  ingested_at: string | null;
  stale: boolean;
};
