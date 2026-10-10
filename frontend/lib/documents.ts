import { API_URL } from "@/lib/api";

export type DocStatus = "uploaded" | "classifying" | "classified" | "indexed" | "extracting" | "review" | "approved" | "failed";

export type DocItem = {
  id: number;
  file: string;
  name: string;
  company: string | null;
  period: string | null;
  doc_type: string | null;
  status: DocStatus;
  error: string | null;
  meta: {
    company?: { slug: string; name_en: string; name_ar: string; ticker: string };
    confidence?: string;
    unit?: string;
    period_end?: string;
    corrected?: boolean;
  };
  size_kb: number;
  indexed: boolean;
  pages: number | null;
  chunks: number | null;
  uploaded_at: string;
};

export type Source = {
  chunk_id: string;
  doc_id: number;
  file: string;
  path?: string;
  page: number;
  section: string;
  text: string;
};

export type Figure = {
  id: string;
  metric: "revenue" | "net_profit" | "eps" | "cash";
  period: string;
  value_text: string;
  unit: string;
  value: number | null;
  value_unit: string;
  quote: string;
  source: Source | null;
  verified: boolean;
  issues: string[];
  existing: number | null;
  include: boolean;
};

export type Segment = {
  id: string;
  name: string;
  share_pct: number | null;
  period: string;
  source: Source | null;
  verified: boolean;
  include: boolean;
  issues: string[];
};

export type Driver = { id: string; en: string; ar: string; source: Source | null; include: boolean; issues: string[] };

export type ReviewContent = {
  company: { slug: string; name_en: string; name_ar: string; ticker: string };
  period: string;
  documents: { id: number; name: string }[];
  figures: Figure[];
  segments: Segment[];
  drivers: Driver[];
  model: string;
  extracted_at: string;
  checks: { figures: number; verified: number };
  approved_at?: string;
  quarter_file?: string;
  current_quarter?: string;
};

export type Review = {
  id: string;
  company: string;
  period: string;
  status: "extracting" | "review" | "approved" | "failed";
  content: ReviewContent;
  error: string | null;
  updated_at: string;
};

export type ReviewListItem = {
  id: string;
  company: string;
  period: string;
  status: Review["status"];
  error: string | null;
  company_name: string | null;
  checks: { figures: number; verified: number } | null;
  updated_at: string;
};

export const METRIC_LABEL: Record<Figure["metric"], string> = {
  revenue: "Revenue",
  net_profit: "Net profit (loss)",
  eps: "Earnings per share",
  cash: "Cash and bank balances",
};

export const STATUS_LABEL: Record<DocStatus, string> = {
  uploaded: "Waiting",
  classifying: "Reading…",
  classified: "Identified",
  indexed: "Indexed",
  extracting: "Extracting figures…",
  review: "Ready for review",
  approved: "Approved",
  failed: "Failed",
};

export const pdfUrl = (s: { path?: string; file: string; page: number }) =>
  `${API_URL}/files/documents/${encodeURIComponent(s.path ?? s.file)}${(s.path ?? s.file).toLowerCase().endsWith(".pdf") ? `#page=${s.page}` : ""}`;

export async function uploadFiles(files: File[]) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  const res = await fetch(`${API_URL}/api/documents/upload`, { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data as { report: { name: string; status: string; reason?: string }[]; documents: DocItem[] };
}

/** The whole source document as a download (original file name). */
export const downloadUrl = (docId: number) => `${API_URL}/api/documents/${docId}/download`;

/** Only the cited page of a PDF, as its own small PDF. */
export const pageExtractUrl = (docId: number, page: number) => `${API_URL}/api/documents/${docId}/pages?start=${page}`;
