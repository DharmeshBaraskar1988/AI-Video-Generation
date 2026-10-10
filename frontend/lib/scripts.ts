export type NodeStatus = {
  name: string;
  status: "pending" | "running" | "done" | "failed" | "waiting" | "stopped";
  started_at?: string;
  finished_at?: string;
  error?: string | null;
  progress?: number;
  detail?: string | null;
};

export type Job = {
  id: string;
  company: string;
  period: string;
  status: "running" | "review" | "audio_review" | "approved" | "narrated" | "rendering" | "done" | "failed" | "stopped";
  stop_requested?: boolean;
  current_node: string | null;
  nodes: NodeStatus[];
  error: string | null;
  files: {
    audio_en?: AudioInfo;
    audio_ar?: AudioInfo;
    video_en?: VideoFile;
    video_ar?: VideoFile;
    notebooklm?: { video: string; poster?: string; duration: number; uploaded_at: string; original_name?: string };
  };
  published?: boolean;
  published_at?: string | null;
  updated_at: string;
};

export type AudioInfo = {
  audio: string; // path under /outputs
  words: string;
  duration: number;
  voice: string;
  engine: string;
  timings_ok: boolean;
  rate?: string;
  preview?: string | null; // voice + music mix for the audio review
  music?: string | null;
  music_volume?: number;
};

export type VideoFile = {
  video: string; // paths under /outputs
  social?: string;
  poster?: string;
  captions?: string;
  props?: string;
  duration: number;
  music: string | null;
  music_credit: string | null;
  rendered_at: string;
};

export type Placeholder = {
  value: number | string;
  display_en: string;
  display_ar: string;
  derived: boolean;
  label: string;
};

export type Scene = {
  id: string;
  type: string;
  en: string;
  ar: string;
  data_keys: string[];
  visual: { chart: string | null; series: string[]; highlight: string | null };
};

export type Checks = {
  numbers_total: number;
  numbers_ok: number;
  stray_numbers: { scene: string; lang: string; text: string }[];
  unknown_placeholders: { scene: string; lang: string; key: string }[];
  placeholder_mismatch: { scene: string; en: string[]; ar: string[] }[];
  passed: boolean;
  repairs: string[];
  words_en: number;
  words_ar: number;
  estimated_seconds_en: number;
  estimated_seconds_ar: number;
  min_seconds: number;
  max_seconds?: number;
  length_ok: boolean;
  enforce_length?: boolean;
};

export type Script = {
  video_id: string;
  company: string;
  company_name_en: string;
  company_name_ar: string;
  quarter: string;
  derived: boolean;
  demo: boolean;
  status: "draft" | "approved";
  target_seconds: number;
  model: string;
  created_at: string;
  scenes: Scene[];
  placeholders: Record<string, Placeholder>;
  checks: Checks;
};

export type ScriptResponse = { job: Job; script: Script | null };

export type ScriptListItem = Job & { script_status: string | null; checks: Checks | null };

export const NODE_LABELS: Record<string, string> = {
  load_quarter: "Load quarter",
  gather_context: "Gather context",
  draft_script: "Draft script (Gemini)",
  factcheck: "Fact-check English",
  translate_ar: "Translate to Arabic (Gemini)",
  factcheck_ar: "Fact-check Arabic",
  human_review: "Human review",
  tts_en: "Narrate English",
  tts_ar: "Narrate Arabic",
  audio_review: "Audio review (voice + music)",
  build_props: "Build video props",
  render_en: "Render English video",
  render_ar: "Render Arabic video",
  mix_audio: "Mix music, social cuts",
  index_script: "Index for video Q&A",
};

export function formatSeconds(total: number): string {
  const m = Math.floor(total / 60);
  const s = Math.round(total % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
