type Lang2 = { en?: string; ar?: string };

export type SummaryItem = {
  en: string; // template, may hold {{F1}} placeholders
  ar?: string;
  display: Lang2; // placeholders filled by Python
  citations: string[]; // keys into Summary.sources (K1, K2, ...)
  verified: boolean;
  unverified: { en?: string[]; ar?: string[] };
};

export type Implication = SummaryItem & { title_en: string; title_ar?: string };

export type Figure = {
  id: string;
  metric_en: string;
  metric_ar?: string;
  current: string; // exactly as printed
  prior: string;
  unit: string;
  change_pct: number | null; // computed in Python
  citations: string[];
  verified: boolean;
  issues: string[];
};

export type Source = {
  id: string;
  doc_id?: number;
  file: string;
  path?: string; // stored file name (uploaded documents)
  page: number;
  section: string;
  note?: string; // "Note 10"
  type: "text" | "table";
  text: string;
};

export type SummaryDocument = {
  title_en: string;
  title_ar?: string;
  issuer_en: string;
  issuer_ar?: string;
  doc_kind: string;
  auditor: string;
  auditor_verified: boolean;
  opinion: string;
  opinion_citations: string[];
  board_approval: string;
  board_citations: string[];
  board_verified: boolean;
};

export type Summary = {
  version: 2;
  company: string;
  period: string;
  names: { name_en: string; name_ar: string };
  document: SummaryDocument;
  period_labels: { current: string; prior: string };
  figures: Figure[];
  executive: SummaryItem;
  implications: Implication[];
  sections: { title_en: string; title_ar?: string; points: SummaryItem[] }[];
  sources: Record<string, Source>;
  documents: { id: number; file: string; path: string; pages: number | null; doc_type: string | null; size_kb: number }[];
  checks: { bullets: number; verified: number; uncited: number; figures: number; figures_verified: number };
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
